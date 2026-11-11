import logging
import threading
import httpx

def send_to_telegram_func(message: str, subject: str, chatid: str = "", token: str = "") -> None:
  """Sends messages via Telegram if both chat id and token are set."""
  try:
    if not chatid or not token:
      logging.info("!!! Telegram ChatID or/and Token is not set...")
      return
    data = {"chat_id": chatid, "text": f"{subject}\n{message}"}
    with httpx.Client(timeout=5) as client:
      response = client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=data)
      if response.status_code != 200:
        logging.error(f"Telegram bot error! Status: {response.status_code} Body: {response.text}")
  except Exception as err:
    logging.error(f"Error while sending message to Telegram: {err}")

def send_to_telegram(message: str, addition_to_subject: str = "") -> None:
  """Non-blocking send. Must be called inside an app context (settings are read from the database here,
  before handing off to the background thread)."""
  try:
    from functions.load_config import get_settings
    settings = get_settings()
  except Exception as err:
    logging.error(f"send_to_telegram(): can't read settings: {err}")
    return
  hostname = settings.get("serverHostname", "")
  subject = f"{addition_to_subject}EasyEmails" + (f" ({hostname})" if hostname else "")
  threading.Thread(target=send_to_telegram_func,
                   args=(message, subject, settings.get("telegramChat", ""), settings.get("telegramToken", "")),
                   daemon=True).start()
