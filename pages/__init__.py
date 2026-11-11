from flask import Blueprint
from .admin_panel import admin_panel_bp
from .domain import domain_bp
from .email_view import email_view_bp
from .fetch import fetch_bp
from .login import login_bp
from .logout import logout_bp
from .logs import logs_bp
from .refresh import refresh_bp
from .reply import reply_bp
from .robots import robots_bp
from .root import root_bp

blueprint = Blueprint("main", __name__)
blueprint.register_blueprint(admin_panel_bp)
blueprint.register_blueprint(domain_bp)
blueprint.register_blueprint(email_view_bp)
blueprint.register_blueprint(fetch_bp)
blueprint.register_blueprint(login_bp)
blueprint.register_blueprint(logout_bp)
blueprint.register_blueprint(logs_bp)
blueprint.register_blueprint(refresh_bp)
blueprint.register_blueprint(reply_bp)
blueprint.register_blueprint(robots_bp)
blueprint.register_blueprint(root_bp)
