"""File system side of the storage: <storagePath>/<domain>/<file>.eml. The database keeps only the path relative to
storagePath, so the whole folder can be moved - just update the setting."""
import logging
import os
import shutil
from pathlib import Path
from db.db import db
from db.database import Email
from functions.load_config import get_settings

def storage_root(create: bool = True) -> Path:
  path = (get_settings().get("storagePath") or "").strip()
  if not path:
    raise RuntimeError("storagePath is not set")
  root = Path(path).resolve()
  if create:
    root.mkdir(parents=True, exist_ok=True)
  return root

def safe_join(root: Path, *parts: str) -> Path:
  """root/parts..., guaranteed to stay inside root (protection against "../" in stored or requested paths)."""
  target = root.joinpath(*parts).resolve()
  if target != root and root not in target.parents:
    raise ValueError(f"path '{target}' is outside of the storage folder '{root}'")
  return target

def save_eml(root: Path, domain: str, filename: str, raw: bytes) -> str:
  """Atomically writes the message into <root>/<domain>/<filename>. Returns the path relative to root."""
  folder = safe_join(root, domain)
  folder.mkdir(parents=True, exist_ok=True)
  target = safe_join(folder, filename)
  tmp = target.with_name(target.name + ".tmp")
  with open(tmp, "wb") as f:
    f.write(raw)
    f.flush()
    os.fsync(f.fileno())
  os.replace(tmp, target)
  return f"{domain}/{filename}"

def email_file(email: Email) -> Path:
  return safe_join(storage_root(create=False), *email.file_path.split("/"))

def read_eml(email: Email) -> bytes:
  with open(email_file(email), "rb") as f:
    return f.read()

def _remove_file(email: Email) -> None:
  try:
    path = email_file(email)
    if path.exists():
      path.unlink()
  except Exception as err:
    logging.error(f"_remove_file(): can't delete file of email id={email.id} ({email.file_path}): {err}")

def _remove_empty_domain_folder(domain: str) -> None:
  try:
    root = storage_root(create=False)
    folder = safe_join(root, domain)
    if folder.parent == root and folder.is_dir() and not any(folder.iterdir()):
      folder.rmdir()
  except Exception as err:
    logging.error(f"_remove_empty_domain_folder(): {domain}: {err}")

def delete_emails(ids: list) -> int:
  """Deletes emails (database rows + .eml files). Returns how many were deleted."""
  if not ids:
    return 0
  emails = Email.query.filter(Email.id.in_(ids)).all()
  domains = {e.domain for e in emails}
  for e in emails:
    _remove_file(e)
    db.session.delete(e)
  db.session.commit()
  for d in domains:
    if Email.query.filter_by(domain=d).count() == 0:
      _remove_empty_domain_folder(d)
  return len(emails)

def delete_domain(domain: str) -> int:
  """Deletes the whole virtual folder: every email of the domain and its folder on disk. Returns emails count.
  The IMAP ledger (FetchedMessage) is kept, so these messages are not imported again."""
  emails = Email.query.filter_by(domain=domain).all()
  for e in emails:
    _remove_file(e)
    db.session.delete(e)
  db.session.commit()
  try:
    root = storage_root(create=False)
    folder = safe_join(root, domain)
    #only ever a direct child of the storage root - never the root itself (domain "." or "")
    if folder.parent == root and folder.is_dir():
      shutil.rmtree(folder)
  except Exception as err:
    logging.error(f"delete_domain(): can't remove folder of domain {domain}: {err}")
  return len(emails)
