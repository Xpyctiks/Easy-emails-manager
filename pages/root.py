import logging
from flask import Blueprint
from flask_login import login_required,current_user
from functions.send_to_telegram import send_to_telegram
from functions.ui_func import render_mail_page

root_bp = Blueprint("root", __name__)

@root_bp.route("/", methods=['GET'])
@login_required
def index():
  """Main page: the three-pane mail view with no domain selected yet."""
  try:
    return render_mail_page()
  except Exception as err:
    logging.error(f"index(): root page general error: {err}")
    send_to_telegram(f"Root page render general error by {current_user.realname}: {err}","🚒")
    return "index(): root page generate function ERROR!", 500
