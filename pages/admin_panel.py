import logging
from flask import redirect,Blueprint,request,render_template,flash
from flask_login import current_user
from db.db import db
from db.database import User, Mailbox, Email
from sqlalchemy import func
from functions.load_config import SETTINGS_SCHEMA, get_settings, save_settings, grouped_settings
from functions.mailbox_func import SECURITY_CHOICES, SMTP_SECURITY_CHOICES, create_mailbox, update_mailbox, delete_mailbox, set_enabled, find_mailbox
from functions.mail_fetch_func import test_mailbox, is_running
from functions.mail_send_func import test_smtp
from functions.rights_required import admin_required, ROLE_NAMES, ADMIN_RIGHTS
from functions.send_to_telegram import send_to_telegram
from functions.users_func import create_user, delete_user, set_role, set_password, find_user

admin_panel_bp = Blueprint("admin_panel", __name__)

def _handler_settings(form) -> str:
  values = {}
  for s in SETTINGS_SCHEMA:
    if s["type"] == "bool":
      values[s["name"]] = "true" if form.get(s["name"]) else "false"
    elif s["name"] in form:
      values[s["name"]] = form.get(s["name"], "")
  save_settings(values)
  logging.info(f"Admin panel: settings saved by {current_user.realname}")
  return "Налаштування збережено."

def _handler_users(form) -> str:
  if "buttonAddUser" in form:
    u = create_user(form.get("new-username"), form.get("new-realname"), form.get("new-password"), form.get("new-role"))
    logging.info(f"Admin panel: user {u.username} ({ROLE_NAMES[u.rights]}) created by {current_user.realname}")
    return f"Користувача \"{u.username}\" створено."
  if "buttonDeleteUser" in form:
    u = find_user(form.get("buttonDeleteUser"))
    if u.id == current_user.id:
      raise ValueError("не можна видалити самого себе")
    delete_user(u.id)
    logging.info(f"Admin panel: user {u.username} deleted by {current_user.realname}")
    return f"Користувача \"{u.username}\" видалено."
  if "buttonSetRole" in form:
    u = find_user(form.get("buttonSetRole"))
    u = set_role(u.id, "user" if u.rights == ADMIN_RIGHTS else "admin")
    logging.info(f"Admin panel: role of {u.username} set to {ROLE_NAMES[u.rights]} by {current_user.realname}")
    return f"Роль користувача \"{u.username}\": {ROLE_NAMES[u.rights]}."
  if "buttonSetPassword" in form:
    uid = form.get("buttonSetPassword")
    u = set_password(uid, form.get(f"password-{uid}", ""))
    logging.info(f"Admin panel: password of {u.username} changed by {current_user.realname}")
    return f"Пароль користувача \"{u.username}\" змінено."
  raise ValueError("невідома дія")

def _mailbox_form(form, prefix: str) -> dict:
  keys = ("name", "host", "port", "security", "username", "password", "folders",
          "smtp_host", "smtp_port", "smtp_security", "smtp_username", "smtp_password")
  #a field missing from the form (not just empty) is left unchanged
  return {key: form.get(f"{prefix}{key}") for key in keys if f"{prefix}{key}" in form}

def _handler_mailboxes(form) -> str:
  if "buttonAddMailbox" in form:
    mb = create_mailbox(_mailbox_form(form, "new-"))
    logging.info(f"Admin panel: mailbox {mb.name} added by {current_user.realname}")
    return f"Скриньку \"{mb.name}\" додано."
  if "buttonEditMailbox" in form:
    mid = form.get("buttonEditMailbox")
    mb = update_mailbox(mid, _mailbox_form(form, f"mb{mid}-"))
    logging.info(f"Admin panel: mailbox {mb.name} updated by {current_user.realname}")
    return f"Скриньку \"{mb.name}\" збережено."
  if "buttonDeleteMailbox" in form:
    mb = delete_mailbox(form.get("buttonDeleteMailbox"))
    logging.info(f"Admin panel: mailbox {mb.name} deleted by {current_user.realname}")
    return f"Скриньку \"{mb.name}\" видалено (зібрані листи залишились)."
  if "buttonToggleMailbox" in form:
    mb = find_mailbox(form.get("buttonToggleMailbox"))
    mb = set_enabled(mb.id, not mb.enabled)
    logging.info(f"Admin panel: mailbox {mb.name} enabled={mb.enabled} by {current_user.realname}")
    return f"Скриньку \"{mb.name}\" {'увімкнено' if mb.enabled else 'вимкнено'}."
  if "buttonTestMailbox" in form:
    mb = find_mailbox(form.get("buttonTestMailbox"))
    try:
      return f"✅ Скринька \"{mb.name}\": підключення успішне. {test_mailbox(mb)}"
    except Exception as err:
      raise ValueError(f"скринька \"{mb.name}\": помилка підключення: {err}")
  if "buttonTestSmtp" in form:
    mb = find_mailbox(form.get("buttonTestSmtp"))
    try:
      return f"✅ Скринька \"{mb.name}\": SMTP підключення та авторизація успішні. {test_smtp(mb)}"
    except Exception as err:
      raise ValueError(f"скринька \"{mb.name}\": помилка SMTP: {err}")
  raise ValueError("невідома дія")

HANDLERS = [
  (("buttonSaveSettings",), _handler_settings, "/admin_panel/settings/"),
  (("buttonAddUser", "buttonDeleteUser", "buttonSetRole", "buttonSetPassword"), _handler_users, "/admin_panel/users/"),
  (("buttonAddMailbox", "buttonEditMailbox", "buttonDeleteMailbox", "buttonToggleMailbox", "buttonTestMailbox", "buttonTestSmtp"), _handler_mailboxes, "/admin_panel/mailboxes/"),
]

@admin_panel_bp.route("/admin_panel/", methods=['POST'])
@admin_required
def catch_admin_panel():
  """POST request processor: every form of the admin panel posts here, the pressed button decides the action."""
  for buttons, handler, back in HANDLERS:
    if any(b in request.form for b in buttons):
      try:
        flash(handler(request.form), "success")
      except ValueError as err:
        flash(f"Помилка: {err}", "danger")
      except Exception as err:
        logging.error(f"catch_admin_panel(): {handler.__name__}: {err}")
        flash("Загальна помилка адмін панелі! Дивіться логи.", "danger")
      return redirect(back, 302)
  logging.error("Something strange was received by /admin_panel via POST request and we can't process that.")
  send_to_telegram(f"Something strange was received by /admin_panel via POST request by {current_user.realname}","🚒")
  flash("Помилка! Жодна з можливих дій не була передана сторінці /admin_panel!", "danger")
  return redirect("/admin_panel/", 302)

@admin_panel_bp.route("/admin_panel/", methods=['GET'])
@admin_required
def admin_panel():
  return redirect("/admin_panel/settings/",302)

@admin_panel_bp.route("/admin_panel/settings/", methods=['GET'])
@admin_required
def admin_panel_settings():
  return render_template("template-admin_panel.html", section="settings", groups=grouped_settings(), settings=get_settings())

@admin_panel_bp.route("/admin_panel/users/", methods=['GET'])
@admin_required
def admin_panel_users():
  users = User.query.order_by(User.username).all()
  return render_template("template-admin_panel.html", section="users", users=users, role_names=ROLE_NAMES, admin_rights=ADMIN_RIGHTS)

@admin_panel_bp.route("/admin_panel/mailboxes/", methods=['GET'])
@admin_required
def admin_panel_mailboxes():
  mailboxes = Mailbox.query.order_by(Mailbox.id).all()
  counts = dict(db.session.query(Email.mailbox_id, func.count(Email.id)).group_by(Email.mailbox_id).all())
  return render_template("template-admin_panel.html", section="mailboxes", mailboxes=mailboxes, counts=counts,
                         security_choices=SECURITY_CHOICES, smtp_security_choices=SMTP_SECURITY_CHOICES, fetch_running=is_running(), settings=get_settings())
