##############################################################################
# INBOUND ENDPOINTS
##############################################################################
import os
from base64 import b64encode
from datetime import datetime

from flask import current_app, request
from sqlalchemy.orm.attributes import flag_modified

from ..data_models import Inbound
from ..database_sqlalchemy import db
from ..prometheus_metrics import metrics
from . import main
from .auth import auth


@main.route("/inbound/check", methods=["POST"])
@metrics.do_not_track()
@metrics.summary(
    "ud_inbound_by_status_current",
    "UD Inbound latencies current",
    labels={"status": lambda r: r.status_code},
)
@metrics.counter(
    "ud_inbound_by_status",
    "UD Inbound invocations counter",
    labels={"status": lambda r: r.status_code},
)
@auth.login_required
def urgency_check():
    """
    Handles inbound queries, returns urgency of query

    Parameters
    ----------
    request (request proxy; see https://flask.palletsprojects.com/en/1.1.x/reqcontext/)
        The request should be sent as JSON with fields:
        - text_to_match (required, string)
        - metadata (optional, list/string/dict/etc.)
            - Any custom metadata

    Returns
    -------
    JSON
        Fields:
    """
    received_ts = datetime.utcnow()

    incoming = request.json
    if "metadata" in incoming:
        incoming_metadata = incoming["metadata"]
    else:
        incoming_metadata = None

    raw_text = incoming["text_to_match"]
    rules = [rule["rule"] for rule in current_app.rules]

    preprocessed_text = current_app.preprocess_text(raw_text)
    urgency_values = current_app.evaluate_rules(preprocessed_text, rules)

    if len(rules) == 0:
        urgency_score = None
    elif any(urgency_values):
        urgency_score = 1.0
    else:
        urgency_score = 0.0

    urgency_values = list(map(float, urgency_values))  # Cast to float

    matched_rules = [
        {
            "rule_id": x["rule_id"],
            "title": x["title"],
            "include": x["rule"].include,
            "exclude": x["rule"].exclude,
        }
        for x, urgency_value in zip(current_app.rules, urgency_values)
        if urgency_value == 1.0
    ]

    processed_ts = datetime.utcnow()
    feedback_secret_key = b64encode(os.urandom(32)).decode("utf-8")

    json_return = dict()
    json_return["urgency_score"] = urgency_score
    json_return["matched_urgency_rules"] = matched_rules
    json_return["feedback_secret_key"] = feedback_secret_key

    new_inbound_query = Inbound(
        feedback_secret_key=feedback_secret_key,
        inbound_text=raw_text,
        inbound_metadata=incoming_metadata,
        inbound_utc=received_ts,
        urgency_score=matched_rules,
        returned_content=json_return,
        returned_utc=processed_ts,
    )

    db.session.add(new_inbound_query)
    db.session.commit()

    json_return["inbound_id"] = new_inbound_query.inbound_id

    return json_return


@main.route("/inbound/feedback", methods=["PUT"])
@metrics.do_not_track()
@metrics.summary(
    "ud_feedback_by_status_current",
    "UD Feedback requests latencies current",
    labels={"status": lambda r: r.status_code},
)
@metrics.counter(
    "ud_feedback_by_status",
    "UD Feedback invocations counter",
    labels={"status": lambda r: r.status_code},
)
@auth.login_required
def inbound_feedback():
    """
    Handles inbound feedback

    Parameters
    ----------
    request (request proxy; see https://flask.palletsprojects.com/en/1.1.x/reqcontext/)
        The request should be sent as JSON with fields:
        - "inbound_id" (required, used to match original inbound query)
        - "feedback_secret_key" (required, used to match original inbound query)
        - "feedback"

    Returns
    -------
    str, HTTP status
        Successful: "Success", 200
        Did not match any previous inbound query: "No Matches", 404
        Matched previous inbound query, but feedback secret key incorrect:
            "Incorrect Feedback Secret Key", 403
    """
    feedback_request = request.json

    orig_inbound = Inbound.query.filter_by(
        inbound_id=feedback_request["inbound_id"]
    ).first()

    if orig_inbound is None:
        return "No Matches", 404
    elif orig_inbound.feedback_secret_key != feedback_request["feedback_secret_key"]:
        return "Incorrect Feedback Secret Key", 403

    if orig_inbound.returned_feedback:
        orig_inbound.returned_feedback.append(feedback_request["feedback"])
        # Need to flag dirty, since modifying JSON object
        # https://docs.sqlalchemy.org/en/14/orm/session_api.htm
        flag_modified(orig_inbound, "returned_feedback")
    else:
        orig_inbound.returned_feedback = [feedback_request["feedback"]]

    db.session.add(orig_inbound)
    db.session.commit()
    return "Success", 200
