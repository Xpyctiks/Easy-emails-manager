# Easy Emails Manager

**Easy Emails Manager** is a web and CLI application that collects all mail from one or more IMAP mailboxes and sorts every message into a **virtual folder per domain**, using either the sender's domain or the recipient's domain (you pick which in the settings). You get a plain web view of everything a domain has received or sent. You don't need a mail client, and you don't have to share the mailbox password with anyone.

Version: **1.0.0**

---

## Features

- **Collection on a GET request.** `GET /fetch/run/` returns `200` right away and starts collecting in the background. You can call it from cron, monitoring or a webhook.
- **Sorting by domain.** Messages are sorted by the sender's domain (`From` → `Sender` → `Return-Path`) or the recipient's domain (a configurable header list, default `To,Cc,X-Original-To,Delivered-To`). If a message has several domains, it goes either to the first one or into every folder as a copy. You can list domains to ignore (for example the collector mailbox's own domain in a catch-all forwarding setup).
- **Three-pane mail interface.** On the left are the virtual folders, one per domain that has at least one message, with the message count, the date of the last message and the total size; you can filter and sort them. In the middle are the messages of the selected domain: sort by received date, sender, recipient, subject, size or mailbox (on the server side), search, and scroll to load more. On the right is the open message. Panes are updated without reloading the page (htmx), every state has its own URL, and the ↑/↓ (J/K) keys move through the messages. On a phone the panes are shown one at a time. Light and dark themes. The folders and the open list refresh themselves every 30 seconds (setting `autoRefresh`): new messages appear highlighted, while the scroll position, checked boxes and the open message are kept.
- **Message view.** The HTML body is shown in a sandboxed iframe: scripts are disabled and remote images are blocked until you choose to show them. You can also see the plain text and the full headers, download attachments, and download the original `.eml`.
- **Replies.** Any user (admin or user) can answer a message right from the reading pane (button or the R key). The reply's sender is, by default, the address the message was sent **to** (for example `info@site-a.com`), and it goes out through the SMTP server configured for the mailbox the message was collected from. The reply is a completely new message: it carries only its own headers, nothing is copied from the original's headers (no `In-Reply-To`/`References`, so mail clients do not group it into the original thread). It can carry attachments, and a copy is stored in the same domain folder, marked "Надіслано". The answered message lists the replies sent to it.
- **Optional deletion on the server.** A message is removed from the IMAP server only *after* its file is written and its database rows are committed.
- **Admin panel.** It has three sections: general settings, users and mailboxes. For each mailbox you set the IMAP account (collecting) and, optionally, the SMTP server (replies); you can test IMAP and SMTP, enable or disable the mailbox and collect from it right away.
- **Roles.** **Admin** gets the admin panel, settings, the log, and can delete messages and domains. **User** sees all domains and messages and can reply to them, but cannot delete anything or open the admin panel. Both roles can reply.
- **CLI** for every main operation.
- **Storage.** Metadata is kept in **MySQL**. The message bodies are stored as `.eml` files in `<storagePath>/<domain>/`.

## Technology Stack

Python 3.11+, Flask, Flask-Login, Flask-SQLAlchemy (SQLAlchemy 2), PyMySQL, click. IMAP and SMTP use the standard library (`imaplib`, `smtplib`).

UI: [Tabler](https://tabler.io) 1.7.1 (a Bootstrap 5 admin theme) and [htmx](https://htmx.org) 2.0.11, both stored locally in `static/vendor/` (no CDN), plus icons from Tabler Icons 3.49.0 embedded as inline SVG (`functions/icons.py`). There is no Node.js build step.

## Project Layout

```
main.py                  Flask app + CLI entry point
db/                      SQLAlchemy models, MySQL URI from .env, automatic adding of new columns
functions/               business logic
  load_config.py         SETTINGS_SCHEMA - every setting, defaults, validation
  mail_fetch_func.py     IMAP collection (background thread, locks)
  mail_parse_func.py     metadata, domain classification, bodies/attachments
  mail_storage_func.py   .eml files on disk
  mail_send_func.py      replies: SMTP connection, reply defaults, sending, stored copy
  domains_func.py        queries for the folders / emails list
  ui_func.py             htmx helpers, three-pane page context, Jinja filters
  icons.py               inline SVG icons
  users_func.py, mailbox_func.py   shared by the admin panel and the CLI
  cli_management.py      CLI commands
pages/                   Flask blueprints (routes)
templates/               mail.html (three panes) + _*.html fragments returned to htmx, admin panel, login, logs
static/                  css/app.css, js/app.js (shared), js/mail.js (mail page), vendor/ (Tabler, htmx)
```

## Installation

```bash
git clone <repo> /opt/Easy-emails-manager
cd /opt/Easy-emails-manager
python3 -m venv venv && . venv/bin/activate
pip install -r requirements.txt
```

Create the database and its user in MySQL. The tables are created automatically on the first start:

```sql
CREATE DATABASE easy_emails CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'easy_emails'@'localhost' IDENTIFIED BY '...';
GRANT ALL PRIVILEGES ON easy_emails.* TO 'easy_emails'@'localhost';
```

Copy `.env.example` to `.env` and fill in the connection details. This is the only thing that lives in `.env`; every other setting is stored in the database.

```
DB_HOST=127.0.0.1
DB_NAME=easy_emails
DB_USER=easy_emails
DB_PASSWORD=...
DB_PORT=3306
DB_SOCKET=          # optional: connect through a unix socket instead of host:port
```

First configuration:

```bash
python main.py show config                       # the first run creates the default settings
python main.py set storagePath /var/lib/easy-emails-manager/mail/
python main.py set logFile /var/log/easy-emails-manager.log
python main.py user add admin "Administrator" 'S3cret!' --admin
python main.py mailbox add main imap.example.com collector@example.com 'mailbox-password'
python main.py mailbox test main
python main.py mailbox upd main --smtp-host smtp.example.com --smtp-security ssl   # optional: replies
python main.py mailbox smtptest main
python main.py fetch run                         # the first collection, in the foreground
```

## Running

```bash
cp gunicorn_config.example.py gunicorn_config.py   # adjust bind/chdir
gunicorn -c gunicorn_config.py
```

Put Nginx (with HTTPS) in front of it. When the app is served over HTTPS, set `SESSION_COOKIE_SECURE = True` in `main.py`.

### Periodic collection (cron)

```cron
*/5 * * * * curl -fsS "http://127.0.0.1:8890/fetch/run/?token=YOUR_FETCH_TOKEN" >/dev/null
```

The response is JSON: `{"status": "started"}` or `{"status": "already running"}`, both with HTTP 200. A wrong token returns `403`. The token check applies only when `fetchToken` is set.

Only one collection runs at a time. A thread lock covers the current process, and MySQL `GET_LOCK()` covers all gunicorn workers and the CLI.

## How Collection Works

1. For each enabled mailbox and each configured folder (default `INBOX`), the app connects (SSL, STARTTLS or plain) and reads `UIDVALIDITY` and the list of UIDs.
2. UIDs that are already in the `fetched_message` ledger are skipped. A message is never downloaded twice, and a message an admin deleted in the app is not imported again.
3. New messages are downloaded with `BODY.PEEK[]`, so they are not marked as read. Each one is sorted into domain folder(s), saved as `<storagePath>/<domain>/<date>_<mailbox>_<folder>_<uidvalidity>_<uid>.eml`, and recorded in the database. The rows and the ledger entry are committed together.
4. When `deleteFromServer` is on, every message that is safely stored is flagged `\Deleted` and expunged. The app uses `UID EXPUNGE` when the server supports UIDPLUS, so only its own messages are touched. This includes messages collected earlier, while deletion was off.
5. Each mailbox's last run time and result appear in the admin panel (Mailboxes tab). Errors are logged and, if Telegram is configured, sent to Telegram.

Messages that have no usable address go to the `_unknown` folder.

Changing `sortBy`, `recipientHeaders`, `multiDomainMode` or `ignoreDomains` affects only newly collected messages. Messages that are already sorted are not moved.

## Replies

Replies are sent through the SMTP server of the mailbox the answered message was collected from (Admin panel → Mailboxes → Змінити → SMTP). An empty SMTP server means replies are disabled for that mailbox, and the reply button is greyed out with the reason. An empty SMTP login means the IMAP login and password are used.

The reply form is prefilled:

- **Від (From):** the address the message was sent to. The candidates are taken from the message's `To`, `Cc`, `X-Original-To`, `Delivered-To` and `Envelope-To`; the default is the one whose domain is the message's folder, otherwise the first `To` address. You can pick another candidate or type any address.
- **Кому (To):** `Reply-To` of the message, otherwise its `From`.
- **Тема:** `Re: <subject>`. The body contains the quoted original text.

The SMTP envelope sender (`MAIL FROM`) is the SMTP login when it is an email address, otherwise the reply's From. Most providers only accept a From that the account owns, so the SMTP account must be allowed to send as those addresses (aliases, a catch-all domain on your own mail server, or a relay).

Both roles (admin and user) can reply; the stored copy records who sent it. You cannot reply to a stored reply (a message marked "Надіслано"). Attachments are limited to 20 MB in total. Ctrl+Enter in the reply text sends it.

## Settings

All settings are stored in the `settings` table (row `id=1`). You can edit them in **Admin panel → Settings** or with `python main.py set <name> <value>`.

| Name | Default | Meaning |
|---|---|---|
| `storagePath` | `/var/lib/easy-emails-manager/mail/` | Main folder; it holds one subfolder per domain |
| `sortBy` | `sender` | `sender` or `recipient` |
| `recipientHeaders` | `To,Cc,X-Original-To,Delivered-To` | Headers used in `recipient` mode, in priority order |
| `multiDomainMode` | `first` | `first`: only the first domain; `all`: a copy in every domain folder |
| `ignoreDomains` | *(empty)* | Comma-separated domains that are never used as a folder |
| `deleteFromServer` | `false` | Delete messages from the IMAP server after they are stored |
| `imapTimeout` | `60` | IMAP and SMTP socket timeout, in seconds |
| `fetchToken` | *(empty)* | When set, `GET /fetch/run/` requires `?token=` |
| `logFile` | `/var/log/easy-emails-manager.log` | Log file (applied after a restart) |
| `sessionKey` | random | Flask session key (applied after a restart) |
| `telegramChat`, `telegramToken` | *(empty)* | Error notifications |
| `serverHostname` | *(empty)* | Shown in page titles and in notifications |
| `autoRefresh` | `30` | How often an open mail page checks for new messages, in seconds; `0` turns it off (takes effect after the page is reloaded) |

To add a setting, add a column to `Settings` (`db/database.py`) and an entry to `SETTINGS_SCHEMA` (`functions/load_config.py`). The admin form and the CLI pick it up automatically.

On every start, columns that exist in the models but are missing in an existing database are added automatically (`db/schema_upgrade.py`, always as NULL-able columns with the model default). Nothing is ever dropped or changed: renaming a column or changing its type still needs a manual `ALTER TABLE`.

## CLI Reference

```
python main.py -h

user add <login> <realname> <password> [--admin]
user del <login>
user setpwd <login> <password>
user setadmin <login>
user unsetadmin <login>

set                                  # list all settings
set <name> <value>                   # e.g. set deleteFromServer on

mailbox add <name> <host> <login> <password> [--security ssl|starttls|none] [--port N] [--folders INBOX,Archive]
            [--smtp-host H] [--smtp-port N] [--smtp-security ssl|starttls|none] [--smtp-username U] [--smtp-password P]
mailbox upd <id|name> [--name ..] [--host ..] [--username ..] [--password ..] [--security ..] [--port ..] [--folders ..]
            [--smtp-host ..] [--smtp-port ..] [--smtp-security ..] [--smtp-username ..] [--smtp-password ..]
mailbox enable|disable|test|smtptest|del <id|name>

fetch run [--mailbox <id|name>]      # collect now, in the foreground
domain del <domain> [--yes]          # delete a domain folder with all its messages

show users | config [--secrets] | mailboxes | domains
version
```

## Web Routes

| Route | Access | Purpose |
|---|---|---|
| `GET /` | user | Mail page, no domain selected |
| `GET /domain/<domain>/` | user | Mail page with a domain open (`sort`, `order`, `q`); for htmx: the list pane, `part=list` (list body), `part=rows&page=N` (next rows) |
| `GET /email/<id>/` | user | Mail page with a message open (`?images=1` shows remote images); for htmx: the reading pane |
| `GET /email/<id>/reply/`, `POST /email/<id>/reply/` | user | Reply form / send the reply |
| `GET /refresh/` | user | Auto-refresh of the mail page (JSON): HTML of the folders and of the list, only for the parts that changed |
| `GET /email/<id>/raw/`, `/email/<id>/attachment/<n>/` | user | Downloads |
| `POST /email/<id>/delete/`, `/domain/<domain>/delete/`, `/domain/<domain>/delete_emails/` | admin | Deletion |
| `GET /fetch/run/` | token | Start collection (cron) |
| `POST /fetch/start/` | admin | "Collect now" button |
| `/admin_panel/…`, `/logs/` | admin | Administration, log viewer |

## Maintenance Mode

When the file `.maintenance` exists in the project root, every request gets a 503 maintenance page (or JSON, for `/fetch/` and AJAX requests). The text inside the file is shown on that page. Delete the file to turn maintenance mode off; no restart is needed.

## Security Notes

- Mailbox passwords (IMAP and SMTP) are stored in the database in plain text, the same way the example project stores its API tokens. Restrict access to the database and use app-specific passwords where your provider offers them.
- Email HTML is shown only inside `<iframe sandbox>` with a restrictive CSP. Attachments are always served as downloads (`Content-Disposition: attachment`, `nosniff`).
- Deleting a mailbox removes its UID ledger. If you add the same mailbox again while `deleteFromServer` is off, its messages are imported again.
