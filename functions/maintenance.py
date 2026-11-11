"""Maintenance mode: while the marker file <project root>/.maintenance exists, every request is answered with a
"system is under maintenance" stub (HTTP 503) instead of being processed. Remove the file to bring the system back;
no restart needed.

  touch /opt/Easy-emails-manager/.maintenance                                  # on
  echo "Оновлення бази даних, до 15:00" > /opt/Easy-emails-manager/.maintenance # on, with a message on the stub
  rm /opt/Easy-emails-manager/.maintenance                                     # off

Static files (/static/...) are still served. A mail fetch that was already running is not interrupted. CLI is not affected."""
import os
import pathlib
from flask import request, jsonify, render_template

MAINTENANCE_FILE = pathlib.Path(__file__).resolve().parent.parent / ".maintenance"
RETRY_AFTER = 300

def _message() -> str:
  try:
    return MAINTENANCE_FILE.read_text(encoding="utf-8", errors="replace").strip()[:500]
  except Exception:
    return ""

def maintenance_guard():
  """before_request hook - must be registered before every other hook."""
  if not os.path.exists(MAINTENANCE_FILE):
    return None
  if request.path.startswith("/static/"):
    return None
  message = _message()
  headers = {"Retry-After": str(RETRY_AFTER), "Cache-Control": "no-store"}
  wants_json = (request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"
                or "application/json" in request.headers.get("Accept", "")
                or request.path.startswith("/fetch/"))
  if wants_json:
    return jsonify({"error": "maintenance", "message": message or "Система в режимі обслуговування"}), 503, headers
  return render_template("maintenance.html", message=message, retry_after=RETRY_AFTER), 503, headers
