"""
Main python script called by gunicorn
"""
import logging
import os

import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

from app import create_app, db
from app.data_models import Inbound, RulesModel

# Log at WARNING level to capture timestamps when FAQs are refreshed
sentry_logging = LoggingIntegration(event_level=logging.WARNING)
sentry_sdk.init(
    integrations=[FlaskIntegration(), sentry_logging],
    traces_sample_rate=os.environ.get("SENTRY_TRANSACTIONS_SAMPLE_RATE"),
)

app = create_app()


@app.shell_context_processor
def make_shell_context():
    """
    Return flask shell with objects imported
    """
    return dict(db=db, Inbound=Inbound, RulesModel=RulesModel)
