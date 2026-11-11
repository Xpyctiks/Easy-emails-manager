import logging
from flask import redirect,flash,Blueprint,session,request
from flask_login import logout_user, login_required, current_user

logout_bp = Blueprint("logout", __name__)

@logout_bp.route("/logout/", methods=['POST'])
@login_required
def do_logout():
  """POST request processor: logs the user out"""
  logging.info(f">>>>>>>>>>>>>>>>>>>>User {current_user.realname} IP:{request.remote_addr} is logging out...")
  logout_user()
  session.clear()
  flash("Ви успішно вийшли із системи!", "info")
  return redirect("/login/",302)

@logout_bp.route("/logout/", methods=['GET'])
@login_required
def show_logout():
  """GET request: nothing should be here. Returns redirect"""
  return redirect("/",302)
