from flask import redirect,flash,request,jsonify
from flask_login import login_required,current_user
from functools import wraps
import logging
from functions.send_to_telegram import send_to_telegram

#rights levels used across the app
USER_RIGHTS = 1      #can only look at the domains and emails
ADMIN_RIGHTS = 255   #admin panel, settings, deleting emails and domains

ROLE_NAMES = {USER_RIGHTS: "Користувач", ADMIN_RIGHTS: "Адміністратор"}

def is_admin() -> bool:
  return bool(current_user.is_authenticated and current_user.rights == ADMIN_RIGHTS)

def rights_required(min_level):
  def decorator(func):
    @wraps(func)
    @login_required
    def wrapper(*args, **kwargs):
      if current_user.rights < min_level:
        logging.warning(f"rights_required(): Attempt to use admin functions ({request.path}) by not privileged user {current_user.realname}")
        send_to_telegram(f"Attempt to use admin functions ({request.path}) by not privileged user {current_user.realname}","🚒")
        if request.headers.get("HX-Request") == "true":
          from functions.ui_func import htmx_response
          return htmx_response(toast=("У вас немає прав на цю дію!", "danger"), reswap="none")
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
          return jsonify({"error": "forbidden"}), 403
        flash('У вас немає прав тут бути!', 'danger')
        return redirect("/",302)
      return func(*args, **kwargs)
    return wrapper
  return decorator

admin_required = rights_required(ADMIN_RIGHTS)
