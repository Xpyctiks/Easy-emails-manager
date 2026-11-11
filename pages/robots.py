from flask import Blueprint, Response

robots_bp = Blueprint("robots", __name__)

@robots_bp.route("/robots.txt", methods=['GET'])
def robots():
  """The app is private - nothing to index."""
  return Response("User-agent: *\nDisallow: /\n", mimetype="text/plain")
