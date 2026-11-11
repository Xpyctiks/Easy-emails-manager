import logging
import smtplib
from flask import render_template,Blueprint,request,redirect,flash,url_for
from flask_login import current_user, login_required
from functions.domains_func import domains_summary
from functions.mail_send_func import reply_defaults, send_reply, MAX_ATTACHMENTS_SIZE
from functions.send_to_telegram import send_to_telegram
from functions.ui_func import is_htmx, htmx_response, list_params, clean_params, render_mail_page, list_page
from pages.email_view import _get_email, email_context

reply_bp = Blueprint("reply", __name__)

def _render_form(email, params, form: dict, error: str = "", status: int = 200):
  """The reply form in the reading pane (htmx fragment or the full three-pane page)."""
  ctx = email_context(email, False)
  if ctx["reply_block"] and not error:
    error = ctx["reply_block"]
  reply = {**form, "error": error}
  if is_htmx():
    body = render_template("_reply_form.html", params=params, reply=reply, max_mb=MAX_ATTACHMENTS_SIZE // 1024 // 1024, **ctx)
    return htmx_response(body, status, push_url=url_for("main.reply.reply_form", email_id=email.id, **clean_params(params)))
  ctx.update(reply=reply, max_mb=MAX_ATTACHMENTS_SIZE // 1024 // 1024)
  return render_mail_page(email.domain, params, email, ctx)

@reply_bp.route("/email/<int:email_id>/reply/", methods=['GET'])
@login_required
def reply_form(email_id):
  """Any logged-in user (admin or user): reply form, prefilled - From = the address the email was sent to, To = Reply-To/From of the email."""
  email = _get_email(email_id)
  params = list_params(request.args)
  if email.is_sent:
    if is_htmx():
      return htmx_response(toast=("Відповідати можна лише на отримані листи.", "warning"), reswap="none")
    return redirect(url_for("main.email_view.show_email", email_id=email.id), 302)
  try:
    defaults = reply_defaults(email, email_context(email, False)["view"])
  except Exception as err:
    logging.error(f"reply_form({email_id}): {err}")
    if is_htmx():
      return htmx_response(toast=(f"Помилка читання листа: {err}", "danger"), reswap="none")
    flash(f"Помилка читання листа: {err}", "danger")
    return redirect(url_for("main.email_view.show_email", email_id=email.id), 302)
  return _render_form(email, params, defaults)

@reply_bp.route("/email/<int:email_id>/reply/", methods=['POST'])
@login_required
def reply_send(email_id):
  """Any logged-in user (admin or user): sends the reply. On an error the form comes back with the entered values and the reason."""
  email = _get_email(email_id)
  params = list_params(request.form)
  form = {k: request.form.get(k, "") for k in ("from_addr", "from_name", "to", "cc", "subject", "body")}
  try:
    form["from_choices"] = reply_defaults(email, email_context(email, False)["view"])["from_choices"]
  except Exception:
    form["from_choices"] = []
  attachments = [(f.filename, f.read()) for f in request.files.getlist("attachments") if f and f.filename]
  try:
    copy = send_reply(email, form, attachments, current_user.realname)
  except ValueError as err:
    return _render_form(email, params, form, f"Помилка: {err}")
  except (smtplib.SMTPException, OSError) as err:
    logging.error(f"reply_send({email_id}): SMTP error: {err}")
    return _render_form(email, params, form, f"Помилка SMTP сервера: {err}")
  except Exception as err:
    logging.error(f"reply_send({email_id}): general error: {err}")
    send_to_telegram(f"Reply sending general error by {current_user.realname}: {err}", "🚒")
    return _render_form(email, params, form, f"Неочікувана помилка: {err}")
  message = "Відповідь надіслано." if copy else "Відповідь надіслано, але зберегти її копію не вдалося (дивіться лог)."
  level = "success" if copy else "warning"
  if not is_htmx():
    flash(message, level)
    return redirect(url_for("main.email_view.show_email", email_id=email.id, **clean_params(params)), 302)
  #reading pane: the original with the new reply listed; OOB: folder counter + refreshed list (the copy is in it)
  info = next((d for d in domains_summary() if d["domain"] == email.domain), None)
  body = render_template("_read_pane.html", params=params, **email_context(email, False))
  body += render_template("_reply_sent_oob.html", domain=email.domain, params=params, domain_info=info,
                          listing=list_page(email.domain, params), email=email)
  return htmx_response(body, toast=(message, level),
                       push_url=url_for("main.email_view.show_email", email_id=email.id, **clean_params(params)))
