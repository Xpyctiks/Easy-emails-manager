"""Mailbox (IMAP account) management shared by the admin panel and the CLI. Raises ValueError on bad input."""
from db.db import db
from db.database import Mailbox, FetchedMessage

SECURITY_CHOICES = {"ssl": "SSL/TLS (993)", "starttls": "STARTTLS (143)", "none": "Без шифрування (143)"}
DEFAULT_PORTS = {"ssl": 993, "starttls": 143, "none": 143}
SMTP_SECURITY_CHOICES = {"ssl": "SSL/TLS (465)", "starttls": "STARTTLS (587)", "none": "Без шифрування (25)"}
SMTP_DEFAULT_PORTS = {"ssl": 465, "starttls": 587, "none": 25}
SMTP_KEYS = ("smtp_host", "smtp_port", "smtp_security", "smtp_username", "smtp_password")

def smtp_configured(mb: Mailbox | None) -> bool:
  """Replies can be sent through this mailbox."""
  return bool(mb is not None and (mb.smtp_host or "").strip())

def _clean_port(value: str, default: int) -> int:
  value = (value or "").strip()
  if value == "":
    return default
  if not value.isdigit() or not 0 < int(value) < 65536:
    raise ValueError("порт має бути числом 1-65535")
  return int(value)

def _clean_smtp(data: dict, existing: Mailbox | None) -> dict:
  """SMTP part of the mailbox form. Empty smtp_host = replies disabled; empty smtp_username = IMAP login/password
  are used for SMTP too (the SMTP password is cleared then); empty smtp_password on edit = keep the current one."""
  result = {k: str(data[k]).strip() for k in SMTP_KEYS if k in data and data[k] is not None}
  if not result:
    return {}
  security = result.get("smtp_security") or (existing.smtp_security if existing and existing.smtp_security else "ssl")
  if security not in SMTP_SECURITY_CHOICES:
    raise ValueError(f"шифрування SMTP: одне з {', '.join(SMTP_SECURITY_CHOICES)}")
  result["smtp_security"] = security
  if "smtp_port" in result or "smtp_security" in data:
    result["smtp_port"] = _clean_port(result.get("smtp_port", ""), SMTP_DEFAULT_PORTS[security])
  if "smtp_username" in result and not result["smtp_username"]:
    result["smtp_password"] = ""
  elif existing is not None and not result.get("smtp_password"):
    result.pop("smtp_password", None)
  return result

def find_mailbox(name_or_id) -> Mailbox:
  mb = None
  if str(name_or_id).isdigit():
    mb = db.session.get(Mailbox, int(name_or_id))
  if mb is None:
    mb = Mailbox.query.filter_by(name=str(name_or_id)).first()
  if mb is None:
    raise ValueError(f"поштову скриньку '{name_or_id}' не знайдено")
  return mb

def _clean(data: dict, existing: Mailbox | None = None) -> dict:
  result = {}
  for key in ("name", "host", "username", "password", "folders", "security", "port"):
    if key in data and data[key] is not None:
      result[key] = str(data[key]).strip()
  if existing is not None and not result.get("password"):
    result.pop("password", None)   #empty password in the edit form = keep the current one
  if "security" in result:
    if result["security"] not in SECURITY_CHOICES:
      raise ValueError(f"шифрування: одне з {', '.join(SECURITY_CHOICES)}")
  if "port" in result:
    if result["port"] == "":
      result["port"] = DEFAULT_PORTS[result.get("security") or (existing.security if existing else "ssl")]
    elif not result["port"].isdigit() or not 0 < int(result["port"]) < 65536:
      raise ValueError("порт має бути числом 1-65535")
    result["port"] = int(result["port"])
  result.update(_clean_smtp(data, existing))
  if "folders" in result:
    result["folders"] = ",".join(f.strip() for f in result["folders"].split(",") if f.strip()) or "INBOX"
  for key in ("name", "host", "username"):
    if key in result and not result[key]:
      raise ValueError(f"поле '{key}' не може бути порожнім")
  if "name" in result:
    other = Mailbox.query.filter_by(name=result["name"]).first()
    if other and (existing is None or other.id != existing.id):
      raise ValueError(f"скринька з назвою '{result['name']}' вже існує")
  return result

def create_mailbox(data: dict) -> Mailbox:
  values = _clean(data)
  for key in ("name", "host", "username", "password"):
    if not values.get(key):
      raise ValueError("назва, сервер, логін та пароль обов'язкові")
  values.setdefault("security", "ssl")
  values.setdefault("port", DEFAULT_PORTS[values["security"]])
  values.setdefault("folders", "INBOX")
  mb = Mailbox(enabled=True, **values)
  db.session.add(mb)
  db.session.commit()
  return mb

def update_mailbox(name_or_id, data: dict) -> Mailbox:
  mb = find_mailbox(name_or_id)
  for key, value in _clean(data, mb).items():
    setattr(mb, key, value)
  db.session.commit()
  return mb

def set_enabled(name_or_id, enabled: bool) -> Mailbox:
  mb = find_mailbox(name_or_id)
  mb.enabled = bool(enabled)
  db.session.commit()
  return mb

def delete_mailbox(name_or_id) -> Mailbox:
  """Deletes the mailbox and its IMAP ledger. Already collected emails stay (they belong to the domains)."""
  mb = find_mailbox(name_or_id)
  FetchedMessage.query.filter_by(mailbox_id=mb.id).delete()
  db.session.delete(mb)
  db.session.commit()
  return mb
