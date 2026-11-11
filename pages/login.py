import logging
from datetime import timedelta
from urllib.parse import urlparse
from flask import render_template,request,redirect,flash,Blueprint,session
from flask_login import login_user,current_user
from db.database import User
from functions.send_to_telegram import send_to_telegram

login_bp = Blueprint("login", __name__)

def _safe_next(target: str) -> str:
  """Only local paths are allowed as a post-login redirect (no open redirect to other sites)."""
  if target and target.startswith("/") and not target.startswith("//") and not urlparse(target).netloc:
    return target
  return "/"

@login_bp.route("/login/", methods=['POST'])
def do_login():
  """POST request processor: logging in the user."""
  try:
    ip = request.remote_addr
    real_ip = request.headers.get('X-Real-IP', '-.-.-.-')
    if current_user.is_authenticated:
      return redirect('/',302)
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "").strip()
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
      session.clear()
      session.permanent = True
      login_user(user, remember=True, duration=timedelta(hours=8))
      logging.info(f">>>>>>>>>>>>>>>>>>>>User {user.realname} logged in successfully. IP: {ip}, Real-IP: {real_ip}")
      return redirect(_safe_next(request.args.get("next", "")),302)
    logging.error(f">>>>>>>>>>>>>>>>>>>>Login: Wrong password for user \"{username}\", IP: {ip}, Real-IP: {real_ip}")
    send_to_telegram(f"Login error! Wrong password for user \"{username}\", IP: {ip}, Real-IP: {real_ip}","🚷")
    flash('Невірний юзер або пароль!', 'danger')
    return redirect(request.full_path if request.args.get("next") else "/login/",302)
  except Exception as err:
    logging.error(f"do_login(): general error: {err}")
    flash("Неочікувана помилка при вході! Дивіться логи!", 'danger')
    return redirect("/login/",302)

@login_bp.route("/login/", methods=['GET'])
def show_login_page():
  """GET request: shows /login page"""
  if current_user.is_authenticated:
    return redirect('/',302)
  return render_template("template-login.html")
