import hmac
import logging
from flask import Blueprint,current_app,jsonify,request,redirect,flash
from flask_login import login_required,current_user
from functions.load_config import get_settings
from functions.mail_fetch_func import start_fetch, is_running
from functions.rights_required import admin_required
from functions.ui_func import is_htmx, htmx_response

fetch_bp = Blueprint("fetch", __name__)

@fetch_bp.route("/fetch/run/", methods=['GET'])
def run_fetch_route():
  """GET request (cron/curl/monitoring): answers 200 right away and starts mail collection from every enabled
  mailbox in background. Protected by Settings.fetchToken (?token=...) when it is set."""
  try:
    token = get_settings().get("fetchToken") or ""
    if token and not hmac.compare_digest(request.args.get("token", ""), token):
      logging.warning(f"run_fetch_route(): wrong token from IP {request.remote_addr}, Real-IP: {request.headers.get('X-Real-IP', '-')}")
      return jsonify({"status": "error", "message": "wrong token"}), 403
    if not start_fetch(current_app._get_current_object()):
      logging.info("run_fetch_route(): previous mail collection is still running, new one is not started")
      return jsonify({"status": "already running"}), 200
    logging.info(f"run_fetch_route(): mail collection started by GET request from IP {request.remote_addr}")
    return jsonify({"status": "started"}), 200
  except Exception as err:
    logging.error(f"run_fetch_route(): Global error: {err}")
    return jsonify({"status": "error", "message": str(err)}), 500

@fetch_bp.route("/fetch/start/", methods=['POST'])
@admin_required
def start_fetch_route():
  """Admin button "collect now" (optionally for one mailbox)."""
  mailbox_id = request.form.get("mailbox_id", "")
  mailbox_id = int(mailbox_id) if mailbox_id.isdigit() else None
  if start_fetch(current_app._get_current_object(), mailbox_id):
    logging.info(f"start_fetch_route(): mail collection started by {current_user.realname} (mailbox: {mailbox_id or 'all'})")
    message, level = "Збір пошти запущено у фоні. Оновіть сторінку за хвилину, результат - у лозі.", "info"
  else:
    message, level = "Збір пошти вже виконується.", "warning"
  if is_htmx():
    return htmx_response(toast=(message, level), reswap="none")
  flash(message, level)
  back = request.form.get("back", "/admin_panel/mailboxes/")
  return redirect(back if back.startswith("/") and not back.startswith("//") else "/", 302)

@fetch_bp.route("/fetch/status/", methods=['GET'])
@login_required
def fetch_status():
  return jsonify({"running": is_running()})
