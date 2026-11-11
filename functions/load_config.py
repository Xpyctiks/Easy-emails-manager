import logging
import secrets
import string
import sys
from db.db import db
from db.database import Settings

#Single source of truth for every program setting (columns of the Settings table, row id=1).
#Drives: default values on the first launch, the admin panel settings form and the CLI "set"/"show config" commands.
#type: "text" | "path" | "int" | "bool" | "choice" | "secret"
SETTINGS_SCHEMA = [
  {"name": "storagePath", "type": "path", "default": "/var/lib/easy-emails-manager/mail/",
   "label": "Головна папка зберігання листів",
   "help": "Всередині створюються папки з назвами доменів, а в них - файли листів (.eml)."},
  {"name": "sortBy", "type": "choice", "default": "sender", "choices": {"sender": "За доменом відправника", "recipient": "За доменом отримувача"},
   "label": "Сортування листів по доменах",
   "help": "Чий домен визначає віртуальну папку листа. Діє на нові листи, вже розсортовані не переносяться."},
  {"name": "recipientHeaders", "type": "text", "default": "To,Cc,X-Original-To,Delivered-To",
   "label": "Заголовки отримувача (по порядку)",
   "help": "Для сортування за отримувачем: заголовки, з яких береться адреса, через кому, в порядку пріоритету."},
  {"name": "multiDomainMode", "type": "choice", "default": "first", "choices": {"first": "Тільки перший домен", "all": "У папку кожного домену (копія)"},
   "label": "Якщо у листа кілька доменів",
   "help": "Наприклад, лист адресовано кільком доменам одночасно."},
  {"name": "ignoreDomains", "type": "text", "default": "",
   "label": "Ігнорувати домени при сортуванні",
   "help": "Через кому. Напр. домен самої скриньки-збирача (gmail.com) при пересиланні catch-all."},
  {"name": "deleteFromServer", "type": "bool", "default": "false",
   "label": "Видаляти листи з поштового сервера",
   "help": "Після того як лист збережено в базі та на диску, оригінал на IMAP сервері видаляється."},
  {"name": "imapTimeout", "type": "int", "default": "60",
   "label": "Таймаут IMAP / SMTP з'єднання (сек.)", "help": ""},
  {"name": "fetchToken", "type": "secret", "default": "",
   "label": "Токен для запуску збору (GET /fetch/run/)",
   "help": "Якщо задано - запит повинен містити ?token=<значення>. Порожньо = без перевірки."},
  {"name": "logFile", "type": "path", "default": "/var/log/easy-emails-manager.log",
   "label": "Файл логу", "help": "Зміна вступає в силу після перезапуску програми."},
  {"name": "sessionKey", "type": "secret", "default": "",
   "label": "Ключ сесій", "help": "Зміна вступає в силу після перезапуску і розлогінює всіх користувачів."},
  {"name": "telegramChat", "type": "text", "default": "", "label": "Telegram ChatID", "help": "Для сповіщень про помилки."},
  {"name": "telegramToken", "type": "secret", "default": "", "label": "Telegram токен бота", "help": ""},
  {"name": "autoRefresh", "type": "int", "min": 0, "default": "30",
   "label": "Автооновлення списків доменів і листів (сек.)",
   "help": "Як часто відкрита сторінка перевіряє нові листи. 0 = вимкнено."},
  {"name": "serverHostname", "type": "text", "default": "", "label": "Назва сервера",
   "help": "Показується в заголовку сторінок і в сповіщеннях Telegram."},
]
SETTINGS_BY_NAME = {s["name"]: s for s in SETTINGS_SCHEMA}
#how the settings are grouped into cards in the admin panel (a setting missing here goes to the last group)
SETTINGS_GROUPS = [
  ("Зберігання та сортування", "folders", ["storagePath", "sortBy", "recipientHeaders", "multiDomainMode", "ignoreDomains"]),
  ("Збір пошти", "mailbox", ["deleteFromServer", "imapTimeout", "fetchToken"]),
  ("Система та сповіщення", "server", ["serverHostname", "autoRefresh", "logFile", "sessionKey", "telegramChat", "telegramToken"]),
]

def grouped_settings() -> list:
  """[(title, icon, [schema entries])] for the admin panel."""
  placed = {n for _, _, names in SETTINGS_GROUPS for n in names}
  groups = [(t, i, [SETTINGS_BY_NAME[n] for n in names if n in SETTINGS_BY_NAME]) for t, i, names in SETTINGS_GROUPS]
  rest = [s for s in SETTINGS_SCHEMA if s["name"] not in placed]
  if rest:
    groups[-1][2].extend(rest)
  return groups

def validate_setting(name: str, value: str) -> str:
  """Checks and normalizes a setting value before it is saved. Raises ValueError with a human readable reason."""
  schema = SETTINGS_BY_NAME.get(name)
  if schema is None:
    raise ValueError(f"невідоме налаштування '{name}'")
  value = (value or "").strip()
  t = schema["type"]
  if t == "bool":
    low = value.lower()
    if low in ("true", "on", "1", "yes"):
      return "true"
    if low in ("false", "off", "0", "no", ""):
      return "false"
    raise ValueError(f"'{name}' приймає true/false (on/off)")
  if t == "int":
    minimum = schema.get("min", 1)
    if not value.isdigit() or int(value) < minimum:
      raise ValueError(f"'{name}' має бути цілим числом не менше {minimum}")
    return str(int(value))
  if t == "choice":
    if value not in schema["choices"]:
      raise ValueError(f"'{name}' приймає одне з: {', '.join(schema['choices'])}")
    return value
  if name in ("storagePath", "logFile", "sessionKey") and not value:
    raise ValueError(f"'{name}' не може бути порожнім")
  if name in ("ignoreDomains", "recipientHeaders"):
    return ",".join(p.strip() for p in value.split(",") if p.strip())
  return value

def get_settings() -> dict:
  """Fresh settings from the database (one cheap query). Used instead of a startup snapshot, so a change made in
  the admin panel or CLI is visible to every gunicorn worker right away."""
  row = db.session.get(Settings, 1)
  result = {}
  for s in SETTINGS_SCHEMA:
    value = getattr(row, s["name"], None) if row else None
    result[s["name"]] = s["default"] if value is None else value
  return result

def is_true(value) -> bool:
  return str(value or "").strip().lower() == "true"

def save_settings(values: dict) -> None:
  """Validates and saves {name: value} into Settings row id=1 (raises ValueError, nothing saved, on a bad value)."""
  clean = {name: validate_setting(name, value) for name, value in values.items()}
  row = db.session.get(Settings, 1)
  for name, value in clean.items():
    setattr(row, name, value)
  db.session.commit()

def _setup_logging(log_file: str) -> None:
  root = logging.getLogger()
  if getattr(root, "_eem_configured", False):
    return
  fmt = logging.Formatter('%(asctime)s - EasyEmails - %(levelname)s - %(message)s', datefmt='%d-%m-%Y %H:%M:%S')
  try:
    handler = logging.FileHandler(log_file, encoding="utf-8")
  except Exception as err:
    print(f"Warning: can't open log file '{log_file}' ({err}), logging to stderr instead", file=sys.stderr)
    handler = logging.StreamHandler(sys.stderr)
  handler.setFormatter(fmt)
  root.addHandler(handler)
  root.setLevel(logging.INFO)
  root._eem_configured = True
  logging.getLogger('werkzeug').setLevel(logging.WARNING)
  logging.getLogger("httpx").setLevel(logging.WARNING)

def load_config(application):
  """Loads the values that must be known at application start (session key, log file) from the database."""
  with application.app_context():
    try:
      settings = get_settings()
      application.config.update({
        "SECRET_KEY": settings["sessionKey"],
        "LOG_FILE": settings["logFile"],
      })
      _setup_logging(settings["logFile"])
    except Exception as msg:
      print(f"Load-config error: {msg}")
      sys.exit(1)

def generate_default_config(application):
  """Checks on every application load that the configuration exists (a Settings row with id=1). If not -
  creates the tables (idempotent, safe on an already-populated database) and inserts default values."""
  with application.app_context():
    db.create_all()
    from db.schema_upgrade import ensure_columns
    ensure_columns()
    if db.session.get(Settings, 1) is None:
      values = {s["name"]: s["default"] for s in SETTINGS_SCHEMA}
      values["sessionKey"] = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(48))
      try:
        db.session.add(Settings(id=1, **values))
        db.session.commit()
        print("First launch. Default settings created in the database. Check them with: python main.py show config")
      except Exception as msg:
        print(f"Generate-default-config error: {msg}")
        sys.exit(1)
