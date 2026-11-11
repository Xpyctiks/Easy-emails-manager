import logging
from urllib.parse import quote
from flask import render_template,Blueprint,request,redirect,flash,Response,url_for,abort
from flask_login import login_required,current_user
from db.db import db
from db.database import Email
from functions.domains_func import domains_summary
from functions.mail_parse_func import message_for_view, attachment_by_index
from functions.mail_storage_func import read_eml, delete_emails
from functions.rights_required import admin_required
from functions.ui_func import is_htmx, htmx_response, list_params, clean_params, render_mail_page, list_page

email_view_bp = Blueprint("email_view", __name__)

def _get_email(email_id: int) -> Email:
  email = db.session.get(Email, email_id)
  if email is None:
    abort(404)
  return email

def _sandbox_html(html: str, allow_images: bool) -> str:
  """HTML of the letter for an <iframe sandbox srcdoc>: no scripts (sandbox), links open in a new tab, and a CSP
  that blocks every remote resource (tracking pixels etc.) unless the user asked to show images."""
  img = "data: https: http:" if allow_images else "data:"
  head = (f'<meta http-equiv="Content-Security-Policy" content="default-src \'none\'; img-src {img}; '
          f'style-src \'unsafe-inline\' data:; font-src data:">'
          '<base target="_blank"><meta name="referrer" content="no-referrer">'
          '<style>body{font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;margin:12px;}</style>')
  return head + html

def email_context(email: Email, allow_images: bool) -> dict:
  """Everything the reading pane needs. Raises FileNotFoundError / parse errors."""
  view = message_for_view(read_eml(email))
  has_remote = bool(view["html"]) and ("http://" in view["html"] or "https://" in view["html"])
  return {"email": email, "view": view, "allow_images": allow_images, "has_remote": has_remote,
          "html": _sandbox_html(view["html"], allow_images) if view["html"] else ""}

def _download(data: bytes, filename: str, mimetype: str) -> Response:
  """Always a download (never rendered by the browser on our origin) - attachments are untrusted content."""
  ascii_name = filename.encode("ascii", "replace").decode().replace('"', "").replace("?", "_") or "file"
  response = Response(data, mimetype=mimetype)
  response.headers["Content-Disposition"] = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
  response.headers["X-Content-Type-Options"] = "nosniff"
  return response

@email_view_bp.route("/email/<int:email_id>/", methods=['GET'])
@login_required
def show_email(email_id):
  """The email (right pane). htmx -> pane fragment, otherwise the full page with its domain and list opened."""
  email = _get_email(email_id)
  params = list_params(request.args)
  allow_images = request.args.get("images") == "1"
  try:
    ctx = email_context(email, allow_images)
  except FileNotFoundError:
    message = f"Файл листа не знайдено на диску: {email.file_path}"
    ctx = None
  except Exception as err:
    logging.error(f"show_email({email_id}): {err}")
    message = f"Помилка читання листа: {err}"
    ctx = None
  if ctx is None:
    if is_htmx():
      return htmx_response(toast=(message, "danger"), reswap="none")
    flash(message, "danger")
    return redirect(url_for("main.domain.show_domain", domain=email.domain, **clean_params(params)), 302)
  if is_htmx():
    body = render_template("_read_pane.html", params=params, **ctx)
    return htmx_response(body, push_url=url_for("main.email_view.show_email", email_id=email.id, **clean_params(params)))
  return render_mail_page(email.domain, params, email, ctx)

@email_view_bp.route("/email/<int:email_id>/raw/", methods=['GET'])
@login_required
def download_raw(email_id):
  email = _get_email(email_id)
  try:
    return _download(read_eml(email), email.file_path.rsplit("/", 1)[-1], "message/rfc822")
  except FileNotFoundError:
    abort(404)

@email_view_bp.route("/email/<int:email_id>/attachment/<int:index>/", methods=['GET'])
@login_required
def download_attachment(email_id, index):
  email = _get_email(email_id)
  try:
    found = attachment_by_index(read_eml(email), index)
  except FileNotFoundError:
    abort(404)
  if found is None:
    abort(404)
  filename, _content_type, payload = found
  return _download(payload, filename, "application/octet-stream")

@email_view_bp.route("/email/<int:email_id>/delete/", methods=['POST'])
@admin_required
def remove_email(email_id):
  """Admin. htmx answer: empty reading pane + the row removed from the list + updated domain counter."""
  email = _get_email(email_id)
  domain = email.domain
  try:
    delete_emails([email.id])
    logging.info(f"remove_email(): email id={email_id} of {domain} deleted by {current_user.realname}")
  except Exception as err:
    logging.error(f"remove_email({email_id}): {err}")
    if is_htmx():
      return htmx_response(toast=(f"Помилка видалення листа: {err}", "danger"), reswap="none")
    flash(f"Помилка видалення листа: {err}", "danger")
    return redirect(url_for("main.domain.show_domain", domain=domain), 302)
  info = next((d for d in domains_summary() if d["domain"] == domain), None)
  if not is_htmx() or info is None:
    flash("Лист видалено." + ("" if info else f" Домен \"{domain}\" тепер порожній."), "success")
    if is_htmx():
      return htmx_response(redirect="/")
    return redirect(url_for("main.domain.show_domain", domain=domain) if info else "/", 302)
  params = list_params(request.form)
  body = render_template("_email_deleted.html", email_id=email_id, domain_info=info, domain=domain, params=params,
                         list_total=list_page(domain, params)["total"])
  return htmx_response(body, toast=("Лист видалено.", "success"),
                       push_url=url_for("main.domain.show_domain", domain=domain, **clean_params(params)))
