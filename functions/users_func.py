"""User management shared by the admin panel and the CLI. Every function raises ValueError with a human readable
reason on bad input, commits on success."""
from werkzeug.security import generate_password_hash
from db.db import db
from db.database import User
from functions.rights_required import USER_RIGHTS, ADMIN_RIGHTS

def _role_to_rights(role: str) -> int:
  role = (role or "user").strip().lower()
  if role == "admin":
    return ADMIN_RIGHTS
  if role == "user":
    return USER_RIGHTS
  raise ValueError("роль має бути 'admin' або 'user'")

def find_user(username_or_id) -> User:
  user = None
  if str(username_or_id).isdigit():
    user = db.session.get(User, int(username_or_id))
  if user is None:
    user = User.query.filter_by(username=str(username_or_id)).first()
  if user is None:
    raise ValueError(f"користувача '{username_or_id}' не знайдено")
  return user

def _admins_count() -> int:
  return User.query.filter_by(rights=ADMIN_RIGHTS).count()

def create_user(username: str, realname: str, password: str, role: str = "user") -> User:
  username, realname, password = (username or "").strip(), (realname or "").strip(), (password or "").strip()
  if not username or not realname or not password:
    raise ValueError("логін, ім'я та пароль обов'язкові")
  if len(username) > 80 or len(realname) > 80:
    raise ValueError("логін та ім'я - не довше 80 символів")
  if User.query.filter_by(username=username).first():
    raise ValueError(f"користувач '{username}' вже існує")
  user = User(username=username, realname=realname, password_hash=generate_password_hash(password), rights=_role_to_rights(role))
  db.session.add(user)
  db.session.commit()
  return user

def set_password(username_or_id, password: str) -> User:
  password = (password or "").strip()
  if not password:
    raise ValueError("пароль не може бути порожнім")
  user = find_user(username_or_id)
  user.password_hash = generate_password_hash(password)
  db.session.commit()
  return user

def set_role(username_or_id, role: str) -> User:
  user = find_user(username_or_id)
  rights = _role_to_rights(role)
  if user.rights == ADMIN_RIGHTS and rights != ADMIN_RIGHTS and _admins_count() <= 1:
    raise ValueError("це останній адміністратор - спочатку призначте іншого")
  user.rights = rights
  db.session.commit()
  return user

def delete_user(username_or_id) -> User:
  user = find_user(username_or_id)
  if user.rights == ADMIN_RIGHTS and _admins_count() <= 1:
    raise ValueError("не можна видалити останнього адміністратора")
  db.session.delete(user)
  db.session.commit()
  return user
