"""Parsing of raw RFC822 messages: metadata for the database, the domain(s) a message is sorted into,
bodies and attachments for the email view page. Everything here is defensive - real-world mail is often broken."""
import base64
import re
from datetime import datetime
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.utils import getaddresses, parsedate_to_datetime

UNKNOWN_DOMAIN = "_unknown"
SENDER_HEADERS = ["From", "Sender", "Return-Path"]
_DOMAIN_RE = re.compile(r"^[a-z0-9_-]+(\.[a-z0-9_-]+)*$")

def normalize_domain(domain: str) -> str:
  """Lowercase, IDNA (punycode) for international names, only [a-z0-9._-]. Anything else -> "" (= not a domain).
  The result is also used as a folder name, so it must never contain path separators or ".."."""
  domain = (domain or "").strip().strip(".").strip("<>[]\"' ").lower()
  if not domain:
    return ""
  try:
    domain = domain.encode("idna").decode("ascii")
  except Exception:
    pass
  if len(domain) > 253 or ".." in domain or not _DOMAIN_RE.match(domain):
    return ""
  return domain

def parse_raw(raw: bytes):
  """Returns (modern EmailMessage for bodies, compat32 Message for tolerant header access)."""
  return message_from_bytes(raw, policy=policy.default), message_from_bytes(raw)

def header_str(msg_compat, name: str, limit: int = 0) -> str:
  """Decoded header value ("=?utf-8?b?...?=" -> text), "" when missing. Never raises."""
  value = msg_compat.get(name)
  if value is None:
    return ""
  try:
    text = str(make_header(decode_header(str(value))))
  except Exception:
    text = str(value)
  text = " ".join(text.split())
  return text[:limit] if limit else text

def header_addresses(msg_compat, name: str) -> list:
  """[(display name, address)] from every occurrence of the header."""
  values = msg_compat.get_all(name) or []
  decoded = []
  for v in values:
    try:
      decoded.append(str(make_header(decode_header(str(v)))))
    except Exception:
      decoded.append(str(v))
  try:
    return [(n, a.strip()) for n, a in getaddresses(decoded) if a and "@" in a]
  except Exception:
    return []

def _domains_from_header(msg_compat, name: str, ignore: set) -> list:
  result = []
  for _, addr in header_addresses(msg_compat, name):
    d = normalize_domain(addr.rsplit("@", 1)[1])
    if d and d not in ignore and d not in result:
      result.append(d)
  return result

def classify_domains(msg_compat, settings: dict) -> list:
  """The domain folder(s) of the message, according to the settings:
  sortBy=sender -> From, Sender, Return-Path; sortBy=recipient -> headers from recipientHeaders (in that order).
  multiDomainMode=first -> the first domain of the first header that gives a not-ignored domain;
  multiDomainMode=all   -> every unique domain of every listed header.
  Nothing found -> [UNKNOWN_DOMAIN]."""
  if settings.get("sortBy") == "recipient":
    headers = [h.strip() for h in (settings.get("recipientHeaders") or "").split(",") if h.strip()] or ["To", "Cc"]
  else:
    headers = SENDER_HEADERS
  ignore = {normalize_domain(d) for d in (settings.get("ignoreDomains") or "").split(",") if d.strip()}
  domains = []
  for h in headers:
    for d in _domains_from_header(msg_compat, h, ignore):
      if d not in domains:
        domains.append(d)
    if domains and settings.get("multiDomainMode") != "all":
      return domains[:1]
  return domains or [UNKNOWN_DOMAIN]

def parse_date(value: str):
  """RFC2822 date -> naive local datetime, None on failure."""
  if not value:
    return None
  try:
    dt = parsedate_to_datetime(value)
    if dt.tzinfo is not None:
      dt = dt.astimezone().replace(tzinfo=None)
    return dt
  except Exception:
    return None

def _part_filename(part) -> str:
  try:
    name = part.get_filename()
  except Exception:
    name = None
  if not name:
    return ""
  try:
    return str(make_header(decode_header(name)))
  except Exception:
    return str(name)

def _is_attachment(part) -> bool:
  if part.is_multipart():
    return False
  disposition = (part.get("Content-Disposition") or "").lower()
  if disposition.startswith("attachment"):
    return True
  #named parts that are not referenced inline as cid: images
  return bool(_part_filename(part)) and not part.get("Content-ID")

def extract_metadata(raw: bytes) -> dict:
  """Everything stored in the Email table about one message (except domain/paths/IMAP data)."""
  msg, msg_compat = parse_raw(raw)
  senders = header_addresses(msg_compat, "From")
  sender_name, sender = (senders[0] if senders else ("", header_str(msg_compat, "From", 512)))
  recipients = []
  for h in ("To", "Cc"):
    recipients += [a for _, a in header_addresses(msg_compat, h)]
  has_attachments = False
  try:
    has_attachments = any(_is_attachment(p) for p in msg.walk())
  except Exception:
    pass
  return {
    "subject": header_str(msg_compat, "Subject", 1000),
    "sender": (sender or "")[:512],
    "sender_name": (sender_name or "")[:512],
    "recipients": ", ".join(dict.fromkeys(recipients)),
    "message_id": header_str(msg_compat, "Message-ID", 512),
    "date_header": parse_date(header_str(msg_compat, "Date")),
    "has_attachments": has_attachments,
  }, msg_compat

def _decode_part(part) -> str:
  try:
    return part.get_content()
  except Exception:
    payload = part.get_payload(decode=True) or b""
    charset = part.get_content_charset() or "utf-8"
    try:
      return payload.decode(charset, errors="replace")
    except LookupError:
      return payload.decode("utf-8", errors="replace")

def _find_body(msg, subtype: str):
  try:
    body = msg.get_body(preferencelist=(subtype,))
    if body is not None:
      return body
  except Exception:
    pass
  for part in msg.walk():
    if part.get_content_type() == f"text/{subtype}" and not _is_attachment(part):
      return part
  return None

def message_for_view(raw: bytes) -> dict:
  """Data for the email view page: decoded headers, text and html bodies (cid: images inlined as data: URIs),
  list of attachments (index = position in msg.walk(), used by the download route)."""
  msg, msg_compat = parse_raw(raw)
  html_part, text_part = _find_body(msg, "html"), _find_body(msg, "plain")
  html = _decode_part(html_part) if html_part is not None else ""
  text = _decode_part(text_part) if text_part is not None else ""
  attachments = []
  cid_map = {}
  for index, part in enumerate(msg.walk()):
    if part.is_multipart():
      continue
    cid = (part.get("Content-ID") or "").strip().strip("<>")
    if cid and part.get_content_maintype() == "image":
      payload = part.get_payload(decode=True) or b""
      cid_map[cid] = f"data:{part.get_content_type()};base64,{base64.b64encode(payload).decode('ascii')}"
    if _is_attachment(part):
      payload = part.get_payload(decode=True) or b""
      attachments.append({"index": index, "filename": _part_filename(part) or f"attachment-{index}",
                          "content_type": part.get_content_type(), "size": len(payload)})
  if html and cid_map:
    html = re.sub(r"cid:([^\"'\s>)]+)", lambda m: cid_map.get(m.group(1), m.group(0)), html)
  headers = []
  for name in msg_compat.keys():
    headers.append((name, header_str(msg_compat, name)))
  return {"html": html, "text": text, "attachments": attachments, "headers": headers,
          "subject": header_str(msg_compat, "Subject"), "from": header_str(msg_compat, "From"),
          "to": header_str(msg_compat, "To"), "cc": header_str(msg_compat, "Cc"),
          "date": header_str(msg_compat, "Date")}

def attachment_by_index(raw: bytes, index: int):
  """(filename, content_type, payload bytes) of the part with that msg.walk() index, or None."""
  msg, _ = parse_raw(raw)
  for i, part in enumerate(msg.walk()):
    if i == index and not part.is_multipart():
      return (_part_filename(part) or f"attachment-{index}", part.get_content_type(), part.get_payload(decode=True) or b"")
  return None

def now() -> datetime:
  return datetime.now().replace(microsecond=0)
