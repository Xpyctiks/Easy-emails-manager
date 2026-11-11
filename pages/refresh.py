import logging
from flask import Blueprint, request, render_template, jsonify
from flask_login import login_required
from functions.domains_func import domains_summary, domains_signature, list_signature
from functions.ui_func import list_params, list_pages, last_fetch, auto_refresh_seconds

refresh_bp = Blueprint("refresh", __name__)
MAX_PAGES = 10   #at most this many infinite-scroll pages are re-rendered (500 rows)

@refresh_bp.route("/refresh/", methods=['GET'])
@login_required
def refresh():
  """Auto-refresh of the mail page (static/js/mail.js polls it). The browser sends what it shows: dsig (folders),
  domain + sort/order/q + lsig (emails list) and how many list pages it has loaded. HTML is returned only for the
  parts whose signature changed, so an idle page costs two light queries per poll."""
  try:
    domains = domains_summary()
    dsig = domains_signature(domains)
    fetched = last_fetch()
    result = {"interval": auto_refresh_seconds(), "dsig": dsig,
              "last_fetch": fetched.strftime('%d.%m.%Y %H:%M') if fetched else "ще не було"}
    domain = request.args.get("domain", "")
    if dsig != request.args.get("dsig"):
      result["domains_html"] = render_template("_domain_list.html", domains=domains, domain=domain)
      result["summary_html"] = render_template("_domains_summary.html", domains=domains,
                                               total_emails=sum(d["count"] for d in domains))
    if domain and any(d["domain"] == domain for d in domains):
      params = list_params(request.args)
      try:
        pages = max(1, min(MAX_PAGES, int(request.args.get("pages", "1"))))
      except ValueError:
        pages = 1
      result["lsig"] = list_signature(domain, params["q"])
      if result["lsig"] != request.args.get("lsig"):
        listing = list_pages(domain, params, pages)
        result["lsig"] = listing["sig"]
        result["list_html"] = render_template("_list_body.html", domain=domain, params=params, listing=listing)
        result["count"] = listing["total"]
    return jsonify(result)
  except Exception as err:
    logging.error(f"refresh(): {err}")
    return jsonify({"error": "refresh failed"}), 500
