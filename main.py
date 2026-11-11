#!/usr/bin/env python3

import pathlib
import os
from dotenv import load_dotenv
from flask import Flask
from flask_login import LoginManager
from db.mysql_uri import build_mysql_uri

if not os.path.exists(pathlib.Path(__file__).resolve().parent / ".env"):
  print(".env file doesn't exists! Can't proceed...")
  exit(1)
load_dotenv(pathlib.Path(__file__).resolve().parent / ".env")
application = Flask(__name__)
application.config["VERSION"] = "1.0.2"
application.config["SQLALCHEMY_DATABASE_URI"] = build_mysql_uri()
application.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
application.config["SQLALCHEMY_ENGINE_OPTIONS"] = (
  {"isolation_level": "READ COMMITTED", "pool_pre_ping": True, "pool_recycle": 3600}
  if application.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql") else {})
application.config['PERMANENT_SESSION_LIFETIME'] = 86400
application.config['SESSION_COOKIE_SECURE'] = False
application.config['SESSION_COOKIE_HTTPONLY'] = True
application.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
#largest accepted request (reply attachments are limited to 20 MB in functions/mail_send_func.py)
application.config['MAX_CONTENT_LENGTH'] = 25 * 1024 * 1024
from db.db import db
from db.database import User
db.init_app(application)
from functions.load_config import load_config, generate_default_config, get_settings
generate_default_config(application)
load_config(application)
application.secret_key = application.config["SECRET_KEY"]
login_manager = LoginManager()
login_manager.login_view = "main.login.show_login_page"
login_manager.login_message = "Необхідно авторизуватись"
login_manager.login_message_category = "warning"
login_manager.session_protection = "strong"
login_manager.init_app(application)
#maintenance mode (marker file .maintenance in the project root) must be checked before anything else touches the DB
from functions.maintenance import maintenance_guard
application.before_request(maintenance_guard)
from functions.cli_management import show_cli

@login_manager.user_loader
def load_user(user_id):
  return db.session.get(User, int(user_id))

@login_manager.unauthorized_handler
def unauthorized():
  """Expired session during an htmx request: send the whole browser tab to the login page, not just one pane."""
  from flask import request, redirect, flash, url_for
  from functions.ui_func import htmx_response
  if request.headers.get("HX-Request") == "true":
    return htmx_response(redirect=url_for("main.login.show_login_page"))
  flash(login_manager.login_message, login_manager.login_message_category)
  return redirect(url_for("main.login.show_login_page", next=request.full_path if request.method == "GET" else None))

from functions.ui_func import register_filters
register_filters(application)

@application.context_processor
def inject_globals():
  """Available in every template: app version, server name (fresh from the DB), admin flag of the current user."""
  from functions.rights_required import is_admin
  try:
    hostname = get_settings().get("serverHostname", "")
  except Exception:
    hostname = ""
  return {"version": application.config.get("VERSION", ""), "server_hostname": hostname, "admin": is_admin()}

from pages import blueprint as routes_blueprint
application.register_blueprint(routes_blueprint)

if __name__ == "__main__":
  show_cli()
