##############################################################################
# INTERNAL ENDPOINTS
##############################################################################
from flask import current_app
from sqlalchemy.exc import SQLAlchemyError

from .. import refresh_evaluator, refresh_rules
from ..database_sqlalchemy import db
from ..prometheus_metrics import metrics
from . import main
from .auth import auth


@main.route("/healthcheck", methods=["GET"])
@metrics.do_not_track()
def healthcheck():
    """
    Check if app can connect to DB
    """
    try:
        db.session.execute("SELECT 1;")
        return "Healthy - Can connect to DB", 200
    except SQLAlchemyError:
        return "Failed DB connection", 500


@main.route("/auth-healthcheck", methods=["GET"])
@metrics.do_not_track()
@auth.login_required
def auth_healthcheck():
    """
    Check if app can connect to DB
    """
    try:
        db.session.execute("SELECT 1;")
        return "Healthy - Can connect to DB", 200
    except SQLAlchemyError:
        return "Failed DB connection", 500


@main.route("/internal/refresh-rules", methods=["GET"])
@metrics.do_not_track()
@auth.login_required
def refresh_rules_endpoint():
    """
    Refresh rules from database
    Must be authenticated
    """
    len_rules = refresh_rules(current_app)
    refresh_evaluator(current_app)
    if len_rules > 0:

        message = f"Successfully refreshed {len_rules} urgency rules"

    else:
        message = f"Successfully refreshed but could not find urgency rules " f"in DB"

    return message, 200
