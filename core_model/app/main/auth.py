import os
from warnings import warn

from flask_httpauth import HTTPTokenAuth

##############################################################################
# AUTHENTICATION SETUP
##############################################################################


auth = HTTPTokenAuth(scheme="Bearer")
tokens = {
    os.getenv("UD_INBOUND_CHECK_TOKEN"): "inbound-check-token",
}


@auth.verify_token
def verify_token(token):
    """Verify inbound check token for urgency detection"""
    if token in tokens:
        return tokens[token]
    else:
        warn("Incorrect Token or not authenticated")
