# Copy to gunicorn_config.py and adjust. Start: gunicorn -c gunicorn_config.py
bind = "127.0.0.1:8890"
workers = 4
threads = 8
worker_class = "gthread"
timeout = 300
keepalive = 30
graceful_timeout = 30
backlog = 2048
loglevel = "info"
chdir = "/opt/Easy-emails-manager"
wsgi_app = "main:application"
