"""Database queries behind the main page (virtual folders = domains) and the domain page (emails table)."""
import math
from sqlalchemy import func, or_
from db.db import db
from db.database import Email

#sortable columns of the emails table: url key -> model column
SORT_COLUMNS = {
  "received": Email.received,
  "subject": Email.subject,
  "sender": Email.sender,
  "recipients": Email.recipients,
  "size": Email.size,
  "mailbox": Email.mailbox_name,
}
PAGE_SIZES = ["50", "100", "250", "500"]
DEFAULT_PAGE_SIZE = "100"

def domains_summary() -> list:
  """[{"domain", "count", "last", "size"}] for every domain that has at least one email."""
  rows = (db.session.query(Email.domain, func.count(Email.id), func.max(Email.received), func.sum(Email.size))
          .group_by(Email.domain).order_by(Email.domain).all())
  return [{"domain": d, "count": c, "last": last, "size": int(size or 0)} for d, c, last, size in rows]

def domain_emails(domain: str, sort: str, order: str, search: str, page: int, per_page: int) -> dict:
  """One page of the domain's emails, sorted and filtered on the database side."""
  query = Email.query.filter(Email.domain == domain)
  if search:
    like = f"%{search}%"
    query = query.filter(or_(Email.subject.ilike(like), Email.sender.ilike(like), Email.sender_name.ilike(like), Email.recipients.ilike(like)))
  total = query.count()
  column = SORT_COLUMNS.get(sort, Email.received)
  primary = column.asc() if order == "asc" else column.desc()
  query = query.order_by(primary, Email.id.desc() if order != "asc" else Email.id.asc())
  total_pages = max(1, math.ceil(total / per_page))
  page = max(1, min(page, total_pages))
  emails = query.offset((page - 1) * per_page).limit(per_page).all()
  return {"emails": emails, "total": total, "page": page, "total_pages": total_pages}

def human_size(size) -> str:
  size = float(size or 0)
  for unit in ("Б", "КБ", "МБ", "ГБ"):
    if size < 1024 or unit == "ГБ":
      return f"{size:.0f} {unit}" if unit == "Б" else f"{size:.1f} {unit}"
    size /= 1024
