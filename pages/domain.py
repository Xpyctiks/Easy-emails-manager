import logging
from flask import render_template,Blueprint,request,redirect,flash,url_for
from flask_login import login_required,current_user
from db.database import Email
from functions.domains_func import domains_summary
from functions.mail_storage_func import delete_domain, delete_emails
from functions.rights_required import admin_required
from functions.ui_func import (is_htmx, htmx_response, list_params, clean_params, list_page, render_mail_page,
                               SORT_LABELS)

domain_bp = Blueprint("domain", __name__)

def _domain_info(domain: str):
  return next((d for d in domains_summary() if d["domain"] == domain), None)

def _clean_url(domain: str, params: dict) -> str:
  return url_for("main.domain.show_domain", domain=domain, **clean_params(params))

@domain_bp.route("/domain/<domain>/", methods=['GET'])
@login_required
def show_domain(domain):
  """The domain's emails (middle pane). htmx requests get fragments:
  part=rows -> next page of rows (infinite scroll); part=list -> list body after sort/search; otherwise the whole pane."""
  try:
    params = list_params(request.args)
    info = _domain_info(domain)
    if info is None:
      if is_htmx():
        return htmx_response(toast=(f"Домену \"{domain}\" не існує або в ньому немає листів.", "warning"), reswap="none")
      flash(f"Домену \"{domain}\" не існує або в ньому немає листів.", "warning")
      return redirect("/",302)
    if not is_htmx():
      return render_mail_page(domain, params)
    part = request.args.get("part", "")
    if part == "rows":
      try:
        page = int(request.args.get("page", "2"))
      except ValueError:
        page = 2
      return render_template("_email_rows.html", domain=domain, params=params, listing=list_page(domain, params, page))
    listing = list_page(domain, params)
    if part == "list":
      body = render_template("_list_body.html", domain=domain, params=params, listing=listing, count_oob=True)
    else:
      body = render_template("_list_pane.html", domain=domain, params=params, listing=listing, domain_count=info["count"],
                             sort_labels=SORT_LABELS, oob=True)
    return htmx_response(body, push_url=_clean_url(domain, params))
  except Exception as err:
    logging.error(f"show_domain({domain}): general error: {err}")
    if is_htmx():
      return htmx_response(toast=("Помилка відображення листів! Дивіться логи.", "danger"), reswap="none")
    flash("Загальна помилка відображення листів! Дивіться логи.", "danger")
    return redirect("/",302)

@domain_bp.route("/domain/<domain>/delete/", methods=['POST'])
@admin_required
def remove_domain(domain):
  """Admin: deletes the whole virtual folder with every email in it."""
  try:
    if Email.query.filter_by(domain=domain).first() is None:
      flash(f"Домен \"{domain}\" не знайдено.", "warning")
      return redirect("/",302)
    count = delete_domain(domain)
    logging.info(f"remove_domain(): domain {domain} deleted with {count} emails by {current_user.realname}")
    flash(f"Домен \"{domain}\" видалено разом з {count} листами.", "success")
  except Exception as err:
    logging.error(f"remove_domain({domain}): {err}")
    flash(f"Помилка видалення домену \"{domain}\": {err}", "danger")
  return redirect("/",302)

@domain_bp.route("/domain/<domain>/delete_emails/", methods=['POST'])
@admin_required
def remove_emails(domain):
  """Admin: deletes the emails selected by checkboxes. htmx answer: refreshed list body + updated domain item."""
  params = list_params(request.form)
  try:
    ids = [int(i) for i in request.form.getlist("email_id") if i.isdigit()]
    #only emails of this domain, whatever ids were posted
    ids = [e.id for e in Email.query.filter(Email.id.in_(ids), Email.domain == domain).all()] if ids else []
    if not ids:
      return htmx_response(toast=("Не обрано жодного листа.", "warning"), reswap="none")
    count = delete_emails(ids)
    logging.info(f"remove_emails(): {count} emails of {domain} deleted by {current_user.realname}")
    info = _domain_info(domain)
    if info is None:
      flash(f"Видалено листів: {count}. Домен \"{domain}\" тепер порожній.", "success")
      return htmx_response(redirect="/")
    body = render_template("_list_body.html", domain=domain, params=params, listing=list_page(domain, params),
                           count_oob=True, domain_info=info, clear_read=True)
    return htmx_response(body, toast=(f"Видалено листів: {count}.", "success"))
  except Exception as err:
    logging.error(f"remove_emails({domain}): {err}")
    return htmx_response(toast=(f"Помилка видалення листів: {err}", "danger"), reswap="none")
