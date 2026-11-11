"""Light automatic schema upgrade: db.create_all() creates missing tables but never changes existing ones, so a column
added to a model later (e.g. Mailbox.smtp_host) would be missing in an already deployed database. On start we compare
every model table with the real one and ADD the missing columns (always as NULL-able, with the model's scalar default).
Nothing is ever dropped or altered - renames/type changes still need a manual ALTER TABLE."""
import logging
from sqlalchemy import inspect, text
from .db import db

def _literal(value, dialect) -> str:
  if isinstance(value, bool):
    return "1" if value else "0"
  if isinstance(value, (int, float)):
    return str(value)
  if isinstance(value, str):
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"
  return ""

def ensure_columns() -> list:
  """Adds missing columns to existing tables. Returns ["table.column", ...] that were added."""
  engine = db.engine
  inspector = inspect(engine)
  quote = engine.dialect.identifier_preparer.quote
  added = []
  for table in db.metadata.sorted_tables:
    if not inspector.has_table(table.name):
      continue
    existing = {c["name"] for c in inspector.get_columns(table.name)}
    for column in table.columns:
      if column.name in existing:
        continue
      ddl = f"ALTER TABLE {quote(table.name)} ADD COLUMN {quote(column.name)} {column.type.compile(dialect=engine.dialect)} NULL"
      default = column.default
      if default is not None and getattr(default, "is_scalar", False):
        literal = _literal(default.arg, engine.dialect)
        if literal:
          ddl += f" DEFAULT {literal}"
      with engine.begin() as conn:
        conn.execute(text(ddl))
      added.append(f"{table.name}.{column.name}")
      logging.info(f"ensure_columns(): added column {table.name}.{column.name}")
  if added:
    print(f"Database schema upgraded, added columns: {', '.join(added)}")
  return added
