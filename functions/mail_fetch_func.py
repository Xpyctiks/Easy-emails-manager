"""Mail collection: for every enabled Mailbox - connect by IMAP, download every message that is not in the
FetchedMessage ledger yet, sort it into domain folder(s) (functions/mail_parse_func.py:classify_domains), save the
.eml file + Email row(s), and - when Settings.deleteFromServer is on - delete the stored messages from the server.

A message is deleted from the server only after its file is written and its database rows are committed.
Started by GET /fetch/run/ (cron), the admin panel button, or the CLI ("python main.py fetch run").
Only one run at a time: a thread lock inside the process + MySQL GET_LOCK() across gunicorn workers/CLI."""
import imaplib
import logging
import re
import ssl
import threading
import time
import zlib
from datetime import datetime
from sqlalchemy import text
from db.db import db
from db.database import Mailbox, Email, FetchedMessage
from functions.load_config import get_settings, is_true
from functions.mail_parse_func import extract_metadata, classify_domains, now
from functions.mail_storage_func import storage_root, save_eml, safe_join
from functions.send_to_telegram import send_to_telegram

LOCK_NAME = "easy_emails_manager_fetch"
STORE_CHUNK = 200
_run_lock = threading.Lock()

class FetchAlreadyRunning(Exception):
  pass

def _quote_folder(folder: str) -> str:
  return '"' + folder.replace("\\", "\\\\").replace('"', '\\"') + '"'

def connect(mb: Mailbox, timeout: int):
  """Logged-in IMAP connection to the mailbox."""
  context = ssl.create_default_context()
  if mb.security == "ssl":
    imap = imaplib.IMAP4_SSL(mb.host, int(mb.port), ssl_context=context, timeout=timeout)
  else:
    imap = imaplib.IMAP4(mb.host, int(mb.port), timeout=timeout)
    if mb.security == "starttls":
      imap.starttls(ssl_context=context)
  imap.login(mb.username, mb.password)
  return imap

def test_mailbox(mb: Mailbox) -> str:
  """Connects, logs in and counts messages in every configured folder. Returns a report, raises on failure."""
  timeout = int(get_settings().get("imapTimeout") or 60)
  imap = connect(mb, timeout)
  try:
    report = []
    for folder in _folders(mb):
      typ, data = imap.select(_quote_folder(folder), readonly=True)
      if typ != "OK":
        report.append(f"{folder}: помилка ({_text(data)})")
      else:
        report.append(f"{folder}: {int(data[0] or 0)} листів")
        imap.close()
    return "; ".join(report)
  finally:
    _logout(imap)

def _text(data) -> str:
  try:
    return " ".join(d.decode(errors="replace") if isinstance(d, bytes) else str(d) for d in (data or []))
  except Exception:
    return str(data)

def _folders(mb: Mailbox) -> list:
  return [f.strip() for f in (mb.folders or "INBOX").split(",") if f.strip()] or ["INBOX"]

def _logout(imap) -> None:
  try:
    imap.logout()
  except Exception:
    pass

def _uidvalidity(imap, qfolder: str) -> int:
  typ, data = imap.response("UIDVALIDITY")
  if data and data[0]:
    return int(data[0])
  typ, data = imap.status(qfolder, "(UIDVALIDITY)")
  m = re.search(rb"UIDVALIDITY (\d+)", data[0] if data and data[0] else b"")
  if not m:
    raise RuntimeError(f"server didn't return UIDVALIDITY for {qfolder}")
  return int(m.group(1))

def _fetch_raw(imap, uid: int):
  """(raw message bytes, INTERNALDATE as naive local datetime or None)"""
  typ, data = imap.uid("FETCH", str(uid), "(INTERNALDATE BODY.PEEK[])")
  if typ != "OK":
    raise RuntimeError(f"UID FETCH {uid} failed: {_text(data)}")
  raw, meta = None, b""
  for item in data or []:
    if isinstance(item, tuple):
      meta += item[0] or b""
      raw = item[1]
    elif isinstance(item, bytes):
      meta += item
  internal = None
  try:
    tt = imaplib.Internaldate2tuple(meta)
    if tt:
      internal = datetime.fromtimestamp(time.mktime(tt))
  except Exception:
    pass
  return raw, internal

def _store_message(imap, mb: Mailbox, folder: str, uidvalidity: int, uid: int, settings: dict, root) -> int:
  """Downloads one message and stores it. Returns number of domain folders it went into."""
  raw, internal = _fetch_raw(imap, uid)
  if raw is None:
    raise RuntimeError(f"UID {uid}: server returned no message body")
  meta, msg_compat = extract_metadata(raw)
  domains = classify_domains(msg_compat, settings)
  received = internal or meta["date_header"] or now()
  filename = f"{received:%Y%m%d-%H%M%S}_{mb.id}_{zlib.crc32(folder.encode()):08x}_{uidvalidity}_{uid}.eml"
  written = []
  try:
    for domain in domains:
      rel = save_eml(root, domain, filename, raw)
      written.append(rel)
      db.session.add(Email(domain=domain, mailbox_id=mb.id, mailbox_name=mb.name, imap_folder=folder,
                           received=received, size=len(raw), file_path=rel, **meta))
    db.session.add(FetchedMessage(mailbox_id=mb.id, folder=folder, uidvalidity=uidvalidity, uid=uid))
    db.session.commit()
  except Exception:
    db.session.rollback()
    for rel in written:
      try:
        safe_join(root, *rel.split("/")).unlink(missing_ok=True)
      except Exception:
        pass
    raise
  return len(domains)

def _delete_on_server(imap, uids: list) -> int:
  """Flags the messages \\Deleted and expunges them (UID EXPUNGE when supported - touches only our messages)."""
  if not uids:
    return 0
  uidplus = b"UIDPLUS" in b" ".join(c if isinstance(c, bytes) else str(c).encode() for c in imap.capabilities)
  for i in range(0, len(uids), STORE_CHUNK):
    chunk = ",".join(str(u) for u in uids[i:i + STORE_CHUNK])
    typ, data = imap.uid("STORE", chunk, "+FLAGS.SILENT", r"(\Deleted)")
    if typ != "OK":
      raise RuntimeError(f"UID STORE \\Deleted failed: {_text(data)}")
    if uidplus:
      imap.uid("EXPUNGE", chunk)
  if not uidplus:
    imap.expunge()
  return len(uids)

def fetch_mailbox(mb: Mailbox, settings: dict, root) -> dict:
  """Collects one mailbox. Returns {"new": n, "errors": n, "deleted": n}."""
  delete = is_true(settings.get("deleteFromServer"))
  timeout = int(settings.get("imapTimeout") or 60)
  stats = {"new": 0, "errors": 0, "deleted": 0}
  imap = connect(mb, timeout)
  try:
    for folder in _folders(mb):
      qfolder = _quote_folder(folder)
      typ, data = imap.select(qfolder, readonly=not delete)
      if typ != "OK":
        raise RuntimeError(f"can't open folder '{folder}': {_text(data)}")
      uidvalidity = _uidvalidity(imap, qfolder)
      typ, data = imap.uid("SEARCH", None, "ALL")
      if typ != "OK":
        raise RuntimeError(f"UID SEARCH failed in '{folder}': {_text(data)}")
      server_uids = [int(x) for x in (data[0] or b"").split()] if data else []
      known = {row.uid for row in db.session.query(FetchedMessage.uid).filter_by(
        mailbox_id=mb.id, folder=folder, uidvalidity=uidvalidity)}
      new_uids = [u for u in server_uids if u not in known]
      #messages stored earlier (e.g. while deleteFromServer was off) are safe to delete too
      stored = [u for u in server_uids if u in known]
      logging.info(f"fetch_mailbox(): {mb.name}/{folder}: {len(server_uids)} on server, {len(new_uids)} new")
      for uid in new_uids:
        try:
          _store_message(imap, mb, folder, uidvalidity, uid, settings, root)
          stored.append(uid)
          stats["new"] += 1
        except (imaplib.IMAP4.abort, OSError):
          raise   #connection is gone - no point to continue with this mailbox
        except Exception as err:
          stats["errors"] += 1
          logging.error(f"fetch_mailbox(): {mb.name}/{folder} UID {uid}: {err}")
      if delete and stored:
        stats["deleted"] += _delete_on_server(imap, sorted(stored))
      imap.close()
  finally:
    _logout(imap)
  return stats

def _acquire_db_lock():
  """Cross-process lock (MySQL GET_LOCK). Returns the connection holding it, None for non-MySQL databases,
  raises FetchAlreadyRunning if another process holds it."""
  if db.engine.dialect.name != "mysql":
    return None
  conn = db.engine.connect()
  got = conn.execute(text("SELECT GET_LOCK(:n, 0)"), {"n": LOCK_NAME}).scalar()
  if got != 1:
    conn.close()
    raise FetchAlreadyRunning()
  return conn

def _release_db_lock(conn) -> None:
  if conn is None:
    return
  try:
    conn.execute(text("SELECT RELEASE_LOCK(:n)"), {"n": LOCK_NAME})
  finally:
    conn.close()

def run_fetch(mailbox_id: int | None = None) -> dict:
  """Collects every enabled mailbox (or just one). Must run inside an app context. Returns per-mailbox stats."""
  lock = _acquire_db_lock()
  try:
    settings = get_settings()
    root = storage_root()
    query = Mailbox.query.order_by(Mailbox.id)
    mailboxes = [m for m in query.all() if (m.id == mailbox_id if mailbox_id else m.enabled)]
    logging.info(f"run_fetch(): -----------------------Starting mail collection, mailboxes: {len(mailboxes)}-----------------------")
    for mb in mailboxes:
      mb.last_status = "⏳ Збір пошти..."
      db.session.commit()
    results = {}
    for mb in mailboxes:
      try:
        stats = fetch_mailbox(mb, settings, root)
        mb.last_status = f"OK: нових {stats['new']}, видалено з сервера {stats['deleted']}" + (f", помилок {stats['errors']}" if stats["errors"] else "")
        mb.last_count = stats["new"]
        if stats["errors"]:
          send_to_telegram(f"Mailbox {mb.name}: {stats['errors']} message(s) failed to import, see the log", "🚒")
      except Exception as err:
        db.session.rollback()
        stats = {"error": str(err)}
        mb.last_status = f"ERROR: {err}"[:1024]
        mb.last_count = 0
        logging.error(f"run_fetch(): mailbox {mb.name}: {err}")
        send_to_telegram(f"Mailbox {mb.name} collection error: {err}", "🚒")
      mb.last_fetch = now()
      db.session.commit()
      results[mb.name] = stats
    logging.info(f"run_fetch(): -----------------------Mail collection finished: {results}-----------------------")
    return results
  finally:
    _release_db_lock(lock)

def start_fetch(app, mailbox_id: int | None = None) -> bool:
  """Starts run_fetch() in a background thread. Returns False if a run is already in progress in this process."""
  if not _run_lock.acquire(blocking=False):
    return False
  threading.Thread(target=_worker, args=(app, mailbox_id), daemon=True).start()
  return True

def is_running() -> bool:
  return _run_lock.locked()

def _worker(app, mailbox_id):
  try:
    with app.app_context():
      try:
        run_fetch(mailbox_id)
      except FetchAlreadyRunning:
        logging.info("run_fetch(): another process is collecting mail right now - this run is skipped")
      except Exception as err:
        db.session.rollback()
        logging.error(f"run_fetch(): global error: {err}")
        send_to_telegram(f"Mail collection global error: {err}", "🚒")
      finally:
        db.session.remove()
  finally:
    _run_lock.release()
