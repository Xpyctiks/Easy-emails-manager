"""CLI: python main.py <group> <command> ...   (python main.py -h for the full list)"""
import logging
import sys
from functools import wraps
import click

def with_app_context(func):
  """Runs the command inside the Flask app context; ValueError -> red message + exit code 1."""
  @wraps(func)
  def wrapper(*args, **kwargs):
    from main import application
    with application.app_context():
      try:
        return func(*args, **kwargs)
      except ValueError as err:
        click.secho(f"Error: {err}", fg="red")
        sys.exit(1)
  return wrapper

@click.group(context_settings=dict(help_option_names=["-h", "--help"]))
def show_cli():
  """Easy Emails Manager CLI"""
  pass

# ---------------------------------------------------------------- USER
@show_cli.group()
def user():
  """User management"""

@user.command("add")
@click.argument("username")
@click.argument("realname")
@click.argument("password")
@click.option("--admin", is_flag=True, help="Create the user with the admin role")
@with_app_context
def user_add(username, realname, password, admin):
  """Add new user (role 'user' unless --admin)"""
  from functions.users_func import create_user
  u = create_user(username, realname, password, "admin" if admin else "user")
  logging.info(f"cli>User '{u.username}' ({u.realname}) created, admin={admin}")
  click.secho(f"User '{u.username}' - '{u.realname}' created successfully{' as admin' if admin else ''}!", fg="green")

@user.command("del")
@click.argument("username")
@with_app_context
def user_del(username):
  """Delete user"""
  from functions.users_func import delete_user
  u = delete_user(username)
  logging.info(f"cli>User '{u.username}' deleted")
  click.secho(f"User '{u.username}' deleted successfully!", fg="green")

@user.command("setpwd")
@click.argument("username")
@click.argument("password")
@with_app_context
def user_setpwd(username, password):
  """Change user password"""
  from functions.users_func import set_password
  u = set_password(username, password)
  logging.info(f"cli>Password of user '{u.username}' changed")
  click.secho(f"Password for user '{u.username}' updated successfully!", fg="green")

@user.command("setadmin")
@click.argument("username")
@with_app_context
def user_setadmin(username):
  """Grant admin role"""
  from functions.users_func import set_role
  u = set_role(username, "admin")
  logging.info(f"cli>User '{u.username}' set as admin")
  click.secho(f"User '{u.username}' is admin now!", fg="green")

@user.command("unsetadmin")
@click.argument("username")
@with_app_context
def user_unsetadmin(username):
  """Make the user a regular (read-only) user"""
  from functions.users_func import set_role
  u = set_role(username, "user")
  logging.info(f"cli>User '{u.username}' set as regular user")
  click.secho(f"User '{u.username}' is a regular user now!", fg="green")

# ---------------------------------------------------------------- SET
def _settings_help() -> str:
  from functions.load_config import SETTINGS_SCHEMA
  lines = []
  for s in SETTINGS_SCHEMA:
    extra = f" [{'|'.join(s['choices'])}]" if s["type"] == "choice" else (" [on|off]" if s["type"] == "bool" else "")
    lines.append(f"  {s['name']}{extra}")
  return "\n".join(lines)

@show_cli.command("set", context_settings=dict(ignore_unknown_options=True))
@click.argument("name", required=False)
@click.argument("value", required=False)
@with_app_context
def set_cmd(name, value):
  """Set a program setting: set <name> <value>. Without arguments - list of settings.
  Use "" for an empty value."""
  from functions.load_config import SETTINGS_BY_NAME, save_settings
  if not name:
    click.echo("Settings:\n" + _settings_help())
    return
  if name not in SETTINGS_BY_NAME:
    lowered = {k.lower(): k for k in SETTINGS_BY_NAME}
    name = lowered.get(name.lower(), name)
  if value is None:
    raise ValueError(f"value is required: set {name} <value>")
  save_settings({name: value})
  logging.info(f"cli>Setting '{name}' updated")
  click.secho(f"Setting '{name}' updated successfully!", fg="green")

# ---------------------------------------------------------------- MAILBOX
@show_cli.group()
def mailbox():
  """Mailboxes (IMAP accounts) to collect mail from"""

@mailbox.command("add")
@click.argument("name")
@click.argument("host")
@click.argument("username")
@click.argument("password")
@click.option("--security", type=click.Choice(["ssl", "starttls", "none"]), default="ssl", show_default=True)
@click.option("--port", default="", help="Default: 993 for ssl, 143 otherwise")
@click.option("--folders", default="INBOX", show_default=True, help="Comma-separated IMAP folders")
@with_app_context
def mailbox_add(name, host, username, password, security, port, folders):
  """Add a mailbox"""
  from functions.mailbox_func import create_mailbox
  mb = create_mailbox({"name": name, "host": host, "username": username, "password": password,
                       "security": security, "port": port, "folders": folders})
  logging.info(f"cli>Mailbox '{mb.name}' added")
  click.secho(f"Mailbox '{mb.name}' (ID {mb.id}) added successfully!", fg="green")

@mailbox.command("upd")
@click.argument("mailbox_id")
@click.option("--name")
@click.option("--host")
@click.option("--username")
@click.option("--password")
@click.option("--security", type=click.Choice(["ssl", "starttls", "none"]))
@click.option("--port")
@click.option("--folders")
@with_app_context
def mailbox_upd(mailbox_id, **fields):
  """Change mailbox parameters (by ID or name)"""
  from functions.mailbox_func import update_mailbox
  mb = update_mailbox(mailbox_id, {k: v for k, v in fields.items() if v is not None})
  logging.info(f"cli>Mailbox '{mb.name}' updated")
  click.secho(f"Mailbox '{mb.name}' updated successfully!", fg="green")

@mailbox.command("del")
@click.argument("mailbox_id")
@with_app_context
def mailbox_del(mailbox_id):
  """Delete a mailbox (collected emails are kept)"""
  from functions.mailbox_func import delete_mailbox
  mb = delete_mailbox(mailbox_id)
  logging.info(f"cli>Mailbox '{mb.name}' deleted")
  click.secho(f"Mailbox '{mb.name}' deleted successfully!", fg="green")

@mailbox.command("enable")
@click.argument("mailbox_id")
@with_app_context
def mailbox_enable(mailbox_id):
  """Enable collecting from the mailbox"""
  from functions.mailbox_func import set_enabled
  mb = set_enabled(mailbox_id, True)
  click.secho(f"Mailbox '{mb.name}' enabled", fg="green")

@mailbox.command("disable")
@click.argument("mailbox_id")
@with_app_context
def mailbox_disable(mailbox_id):
  """Disable collecting from the mailbox"""
  from functions.mailbox_func import set_enabled
  mb = set_enabled(mailbox_id, False)
  click.secho(f"Mailbox '{mb.name}' disabled", fg="yellow")

@mailbox.command("test")
@click.argument("mailbox_id")
@with_app_context
def mailbox_test(mailbox_id):
  """Check connection and login"""
  from functions.mailbox_func import find_mailbox
  from functions.mail_fetch_func import test_mailbox
  mb = find_mailbox(mailbox_id)
  try:
    click.secho(f"OK: {test_mailbox(mb)}", fg="green")
  except Exception as err:
    click.secho(f"Connection error: {err}", fg="red")
    sys.exit(1)

# ---------------------------------------------------------------- FETCH
@show_cli.group()
def fetch():
  """Mail collection"""

@fetch.command("run")
@click.option("--mailbox", "mailbox_id", default=None, help="Only this mailbox (ID or name), even if disabled")
@with_app_context
def fetch_run(mailbox_id):
  """Collect mail right now (in the foreground)"""
  from functions.mail_fetch_func import run_fetch, FetchAlreadyRunning
  from functions.mailbox_func import find_mailbox
  mb_id = find_mailbox(mailbox_id).id if mailbox_id else None
  logging.info("-----------------------Starting CLI functions: fetch run")
  try:
    results = run_fetch(mb_id)
  except FetchAlreadyRunning:
    click.secho("Mail collection is already running in another process", fg="yellow")
    sys.exit(1)
  if not results:
    click.echo("No enabled mailboxes.")
  failed = False
  for name, stats in results.items():
    if "error" in stats:
      failed = True
      click.secho(f"{name}: ERROR {stats['error']}", fg="red")
    else:
      click.secho(f"{name}: new {stats['new']}, deleted on server {stats['deleted']}, errors {stats['errors']}",
                  fg="yellow" if stats["errors"] else "green")
  sys.exit(1 if failed else 0)

# ---------------------------------------------------------------- DOMAIN
@show_cli.group()
def domain():
  """Virtual domain folders"""

@domain.command("del")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Don't ask for confirmation")
@with_app_context
def domain_del(name, yes):
  """Delete a domain folder with all its emails"""
  from db.database import Email
  from functions.mail_storage_func import delete_domain
  count = Email.query.filter_by(domain=name).count()
  if count == 0:
    raise ValueError(f"domain '{name}' has no emails")
  if not yes and not click.confirm(f"Delete domain '{name}' with {count} email(s)?", default=False):
    click.echo("Cancelled.")
    return
  deleted = delete_domain(name)
  logging.info(f"cli>Domain '{name}' deleted with {deleted} emails")
  click.secho(f"Domain '{name}' deleted ({deleted} emails)", fg="green")

# ---------------------------------------------------------------- SHOW
@show_cli.group()
def show():
  """Show information"""

@show.command("users")
@with_app_context
def show_users():
  from db.database import User
  from functions.rights_required import ROLE_NAMES
  users = User.query.order_by(User.username).all()
  if not users:
    click.echo("No users found in DB! Add one: python main.py user add <login> <name> <password> --admin")
  for u in users:
    click.echo(f"ID: {u.id}, Login: {u.username}, RealName: {u.realname}, Role: {ROLE_NAMES.get(u.rights, u.rights)}, Created: {u.created:%d.%m.%Y %H:%M}")

@show.command("config")
@click.option("--secrets", is_flag=True, help="Show secret values too")
@with_app_context
def show_config(secrets):
  from functions.load_config import SETTINGS_SCHEMA, get_settings
  settings = get_settings()
  width = max(len(s["name"]) for s in SETTINGS_SCHEMA)
  for s in SETTINGS_SCHEMA:
    value = settings[s["name"]]
    if s["type"] == "secret" and value and not secrets:
      value = "******"
    click.echo(f"{s['name']:<{width}}  {value}")

@show.command("mailboxes")
@with_app_context
def show_mailboxes():
  from db.database import Mailbox
  boxes = Mailbox.query.order_by(Mailbox.id).all()
  if not boxes:
    click.echo("No mailboxes. Add one: python main.py mailbox add <name> <host> <login> <password>")
  for m in boxes:
    last = f"{m.last_fetch:%d.%m.%Y %H:%M}" if m.last_fetch else "never"
    click.echo(f"ID: {m.id}, Name: {m.name}, {m.username}@{m.host}:{m.port} ({m.security}), Folders: {m.folders}, "
               f"Enabled: {m.enabled}, Last fetch: {last} - {m.last_status or ''}")

@show.command("domains")
@with_app_context
def show_domains():
  from functions.domains_func import domains_summary
  rows = domains_summary()
  if not rows:
    click.echo("No emails yet.")
  for r in rows:
    click.echo(f"{r['domain']:<40} {r['count']:>7} emails, last: {r['last']:%d.%m.%Y %H:%M}")

# ---------------------------------------------------------------- VERSION
@show_cli.command("version")
def show_version():
  """Show application version"""
  from main import application
  click.echo(application.config.get("VERSION", ""))
