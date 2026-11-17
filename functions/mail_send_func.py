"""Replies to collected emails: SMTP connection of a mailbox, default values of the reply form, building and sending
the reply. The reply's sender (From) is by default the address the original email was sent TO - e.g. a letter that
came to info@site-a.com (collected through a catch-all mailbox) is answered from info@site-a.com.

The sent reply is stored like any other email (.eml + Email row with is_sent=True) in the same domain folder as the
email it answers, so the conversation stays together."""
import logging
import mimetypes
import re
import smtplib
import ssl
import uuid
from email.message import EmailMessage
from email.utils import formataddr, formatdate, getaddresses, make_msgid
from db.db import db
from db.database import Email, Mailbox
from functions.load_config import get_settings
from functions.mail_parse_func import parse_raw, header_addresses, header_str, normalize_domain, now
from functions.mail_storage_func import storage_root, save_eml, read_eml
from functions.mailbox_func import SMTP_DEFAULT_PORTS

#headers of the ORIGINAL email whose addresses can be used as the sender of the reply, in priority order
RECIPIENT_HEADERS = ["To", "Cc", "X-Original-To", "Delivered-To", "Envelope-To"]
MAX_ATTACHMENTS_SIZE = 20 * 1024 * 1024
QUOTE_MAX_LINES = 400
_ADDRESS_RE = re.compile(r"^[^@\s<>()\[\],;:\"]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")

def _timeout() -> int:
  try:
    return int(get_settings().get("imapTimeout") or 60)
  except ValueError:
    return 60

def smtp_credentials(mb: Mailbox) -> tuple:
  """(login, password): the SMTP ones, or the IMAP ones when no SMTP login is set."""
  if (mb.smtp_username or "").strip():
    return mb.smtp_username.strip(), mb.smtp_password or ""
  return mb.username, mb.password

def smtp_connect(mb: Mailbox):
  """Logged-in SMTP connection of the mailbox (use as a context manager - it quits on exit)."""
  security = mb.smtp_security or "ssl"
  port = int(mb.smtp_port or SMTP_DEFAULT_PORTS.get(security, 465))
  context = ssl.create_default_context()
  if security == "ssl":
    smtp = smtplib.SMTP_SSL(mb.smtp_host, port, timeout=_timeout(), context=context)
  else:
    smtp = smtplib.SMTP(mb.smtp_host, port, timeout=_timeout())
    smtp.ehlo()
    if security == "starttls":
      smtp.starttls(context=context)
      smtp.ehlo()
  login, password = smtp_credentials(mb)
  if login:
    try:
      smtp.login(login, password)
    except Exception:
      smtp.close()
      raise
  return smtp

def test_smtp(mb: Mailbox) -> str:
  """Connects and logs in, sends nothing. Returns a report, raises on failure."""
  if not (mb.smtp_host or "").strip():
    raise ValueError("SMTP сервер не задано")
  with smtp_connect(mb) as smtp:
    smtp.noop()
  return f"{mb.smtp_host}:{mb.smtp_port} ({mb.smtp_security}), логін {smtp_credentials(mb)[0]}"

def parse_addresses(text: str, field: str, required: bool = True) -> list:
  """'Name <a@b.c>, d@e.f' -> [(name, address)]. Raises ValueError with the field name on a bad address."""
  text = (text or "").replace("\r", " ").replace("\n", " ").strip()
  if not text:
    if required:
      raise ValueError(f"поле «{field}» не може бути порожнім")
    return []
  result = []
  for name, address in getaddresses([text]):
    address = address.strip()
    if not _ADDRESS_RE.match(address):
      raise ValueError(f"некоректна адреса в полі «{field}»: {address or text}")
    result.append((name.strip(), address))
  if required and not result:
    raise ValueError(f"поле «{field}» не може бути порожнім")
  return result

def _html_to_text(html: str) -> str:
  text = re.sub(r"(?is)<(script|style|head).*?</\1>", "", html)
  text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h[1-6]>", "\n", text)
  text = re.sub(r"<[^>]+>", "", text)
  import html as _html
  text = _html.unescape(text)
  return re.sub(r"\n{3,}", "\n\n", text).strip()

def reply_defaults(email: Email, view: dict) -> dict:
  """Initial values of the reply form for the original email (its parsed `view` from message_for_view)."""
  _, msg_compat = parse_raw(read_eml(email))
  candidates = []
  for header in RECIPIENT_HEADERS:
    for name, address in header_addresses(msg_compat, header):
      if address.lower() not in {a.lower() for _, a in candidates}:
        candidates.append((name, address))
  #best sender: an address of the domain the email is sorted into, otherwise the first recipient
  default = next((c for c in candidates if normalize_domain(c[1].rsplit("@", 1)[-1]) == email.domain), None)
  default = default or (candidates[0] if candidates else ("", ""))
  reply_to = header_addresses(msg_compat, "Reply-To") or header_addresses(msg_compat, "From")
  subject = view.get("subject") or email.subject or ""
  if not re.match(r"(?i)^\s*(re|ответ|відп)\s*:", subject):
    subject = f"Re: {subject}".strip()
  original_text = view.get("text") or _html_to_text(view.get("html") or "")
  quoted = "\n".join("> " + line for line in original_text.splitlines()[:QUOTE_MAX_LINES])
  when = (email.date_header or email.received).strftime("%d.%m.%Y %H:%M")
  who = header_str(msg_compat, "From") or email.sender
  return {
    "from_choices": candidates,
    "from_addr": default[1],
    "from_name": default[0],
    "to": ", ".join(formataddr(a) for a in reply_to),
    "cc": "",
    "subject": subject,
    "body": f"\n\n{when}, {who} пише:\n{quoted}\n" if quoted else "\n",
  }

def build_reply(original: Email, from_name: str, from_addr: str, to: list, cc: list, subject: str, body: str,
                attachments: list) -> EmailMessage:
  """attachments: [(filename, bytes)]
  The reply is a brand-new message: only its own headers (From, To, Cc, Subject, Date, Message-ID, MIME). Nothing is
  copied from the original - no In-Reply-To / References, so the original's Message-ID and thread never leave the
  program. The link to the original is kept only in the database (Email.in_reply_to) for the "replies" card."""
  msg = EmailMessage()
  msg["From"] = formataddr((from_name.replace("\n", " ").strip(), from_addr))
  msg["To"] = ", ".join(formataddr(a) for a in to)
  if cc:
    msg["Cc"] = ", ".join(formataddr(a) for a in cc)
  msg["Subject"] = " ".join((subject or "").split())
  msg["Date"] = formatdate(localtime=True)
  msg["Message-ID"] = make_msgid(domain=from_addr.rsplit("@", 1)[1])
  msg.set_content(body.replace("\r\n", "\n"))
  for filename, data in attachments:
    ctype, _ = mimetypes.guess_type(filename)
    maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
    msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
  return msg

def send_reply(original: Email, form: dict, attachments: list, sent_by: str) -> Email | None:
  """Validates the form, sends the reply through the SMTP server of the mailbox the original came from and stores
  a copy. Raises ValueError (bad input / no SMTP) or the SMTP error. Returns the stored copy (None if only storing
  failed - the reply itself was sent then)."""
  from functions.mail_parse_func import extract_metadata
  if original.is_sent:
    raise ValueError("це вже надісланий лист - відповідати можна лише на отримані")
  mb = db.session.get(Mailbox, original.mailbox_id) if original.mailbox_id else None
  if mb is None or not (mb.smtp_host or "").strip():
    raise ValueError("для скриньки цього листа не налаштовано SMTP сервер (Адміністрування → Поштові скриньки)")
  from_addr = (form.get("from_addr") or "").strip()
  if not _ADDRESS_RE.match(from_addr):
    raise ValueError(f"некоректна адреса відправника: {from_addr or '(порожньо)'}")
  to = parse_addresses(form.get("to"), "Кому")
  cc = parse_addresses(form.get("cc"), "Копія", required=False)
  body = form.get("body") or ""
  if not body.strip():
    raise ValueError("текст відповіді порожній")
  if sum(len(d) for _, d in attachments) > MAX_ATTACHMENTS_SIZE:
    raise ValueError(f"вкладення разом більші за {MAX_ATTACHMENTS_SIZE // 1024 // 1024} МБ")
  msg = build_reply(original, form.get("from_name") or "", from_addr, to, cc, form.get("subject") or "", body, attachments)
  login = smtp_credentials(mb)[0]
  #authenticated servers usually require the envelope sender to be the account itself; From stays the reply address
  envelope_from = login if "@" in (login or "") else from_addr
  with smtp_connect(mb) as smtp:
    refused = smtp.send_message(msg, from_addr=envelope_from, to_addrs=[a for _, a in to + cc])
  logging.info(f"send_reply(): reply to email id={original.id} sent by {sent_by} from {from_addr} to "
               f"{', '.join(a for _, a in to + cc)} via {mb.name} ({mb.smtp_host}){f', refused: {refused}' if refused else ''}")
  raw = msg.as_bytes()
  try:
    stamp = now()
    rel = save_eml(storage_root(), original.domain, f"{stamp:%Y%m%d-%H%M%S}_sent_{uuid.uuid4().hex[:12]}.eml", raw)
    meta, _ = extract_metadata(raw)
    copy = Email(domain=original.domain, mailbox_id=mb.id, mailbox_name=mb.name, imap_folder="(надіслано)",
                 received=stamp, size=len(raw), file_path=rel, is_sent=True,
                 in_reply_to=original.message_id or "", sent_by=sent_by, **meta)
    db.session.add(copy)
    db.session.commit()
    return copy
  except Exception as err:
    db.session.rollback()
    logging.error(f"send_reply(): reply was SENT, but storing its copy failed: {err}")
    return None
