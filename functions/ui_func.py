"""Helpers of the web UI: htmx detection/response headers, the three-pane mail page context, Jinja filters.

UI model: one page with three panes (domains | emails of the domain | the email). Navigation inside the page is done
by htmx - it requests a pane fragment and swaps it in place, the server tells the browser which clean URL to show
(HX-Push-Url), so every state has a normal URL that renders the full page on reload."""
import hashlib
import json
import zlib
from datetime import datetime, timedelta
from flask import request, make_response, render_template
from sqlalchemy import func
from db.db import db
from db.database import Mailbox
from functions.domains_func import domains_summary, domain_emails, SORT_COLUMNS

LIST_PAGE_SIZE = 50
SORT_LABELS = {"received": "Дата отримання", "sender": "Відправник", "recipients": "Отримувач",
               "subject": "Тема", "size": "Розмір", "mailbox": "Скринька"}

def is_htmx() -> bool:
  return request.headers.get("HX-Request") == "true"

def toast_header(message: str, level: str = "success") -> dict:
  """HX-Trigger header that makes static/js/app.js show a toast. JSON is ASCII-escaped: headers must be latin-1."""
  return {"HX-Trigger": json.dumps({"showToast": {"message": message, "level": level}})}

def htmx_response(body: str = "", status: int = 200, toast: tuple | None = None, push_url: str | None = None,
                  redirect: str | None = None, reswap: str | None = None):
  response = make_response(body, status)
  if toast:
    response.headers.update(toast_header(*toast))
  if push_url:
    response.headers["HX-Push-Url"] = push_url
  if redirect:
    response.headers["HX-Redirect"] = redirect
  if reswap:
    response.headers["HX-Reswap"] = reswap
  return response

def list_params(args) -> dict:
  """Normalized sort/order/search of the emails list from the query string."""
  sort = args.get("sort", "received")
  if sort not in SORT_COLUMNS:
    sort = "received"
  order = "asc" if args.get("order") == "asc" else "desc"
  return {"sort": sort, "order": order, "q": (args.get("q") or "").strip()[:200]}

def clean_params(params: dict) -> dict:
  """Only non-default values - for short URLs."""
  result = {}
  if params.get("sort", "received") != "received":
    result["sort"] = params["sort"]
  if params.get("order", "desc") != "desc":
    result["order"] = params["order"]
  if params.get("q"):
    result["q"] = params["q"]
  return result

def list_page(domain: str, params: dict, page: int = 1) -> dict:
  return domain_emails(domain, params["sort"], params["order"], params["q"], page, LIST_PAGE_SIZE)

def last_fetch():
  return db.session.query(func.max(Mailbox.last_fetch)).scalar()

def render_mail_page(domain: str | None = None, params: dict | None = None, email=None, email_ctx: dict | None = None):
  """Full three-pane page. `pane_view` tells which pane is shown on narrow (mobile) screens."""
  params = params or list_params({})
  domains = domains_summary()
  ctx = {"domains": domains, "total_emails": sum(d["count"] for d in domains), "last_fetch": last_fetch(),
         "domain": domain, "params": params, "sort_labels": SORT_LABELS, "email": email,
         "pane_view": "read" if email else ("list" if domain else "domains")}
  if domain:
    ctx["listing"] = list_page(domain, params)
    ctx["domain_count"] = next((d["count"] for d in domains if d["domain"] == domain), 0)
  if email_ctx:
    ctx.update(email_ctx)
  return render_template("mail.html", **ctx)

# ---------------------------------------------------------------- Jinja filters
_MONTHS = ["січ.", "лют.", "бер.", "квіт.", "трав.", "черв.", "лип.", "серп.", "вер.", "жовт.", "лист.", "груд."]
_AVATAR_COLORS = ["blue", "azure", "indigo", "purple", "pink", "red", "orange", "yellow", "lime", "green", "teal", "cyan"]

def short_date(dt) -> str:
  """Mail-client style: 10:42 today, "вчора" yesterday, "9 лист." this year, 09.11.2024 otherwise."""
  if not dt:
    return ""
  today = datetime.now().date()
  if dt.date() == today:
    return dt.strftime("%H:%M")
  if dt.date() == today - timedelta(days=1):
    return "вчора"
  if dt.year == today.year:
    return f"{dt.day} {_MONTHS[dt.month - 1]}"
  return dt.strftime("%d.%m.%Y")

def initials(name: str, address: str = "") -> str:
  words = [w for w in (name or "").replace('"', "").split() if w[:1].isalnum()]
  if len(words) >= 2:
    return (words[0][0] + words[1][0]).upper()
  if words:
    return words[0][:2].upper()
  return (address or "?")[:1].upper()

def avatar_color(key: str) -> str:
  return _AVATAR_COLORS[zlib.crc32((key or "").lower().encode()) % len(_AVATAR_COLORS)]

def dom_id(domain: str) -> str:
  """Safe HTML id for a domain item (domains contain dots)."""
  return "dom-" + hashlib.md5(domain.encode()).hexdigest()[:12]

def register_filters(app) -> None:
  from functions.icons import icon
  from functions.domains_func import human_size
  app.jinja_env.globals.update(icon=icon, human_size=human_size, clean_params=clean_params)
  app.jinja_env.filters.update(short_date=short_date, initials=initials, avatar_color=avatar_color, dom_id=dom_id)
