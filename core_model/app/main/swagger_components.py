from xml.etree.ElementInclude import include

from flask_restx import Api, fields, reqparse

from . import main

# Security
authorizations = {
    "Bearer": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
        "description": (
            "In the *'Value'* input box below, enter "
            "**'Bearer &lt;JWT&gt;'**, where JWT is the token"
        ),
    }
}
api = Api(
    main,
    title="MomConnect AAQ UD API",
    authorizations=authorizations,
    security="Bearer",
)

# Inbound fields
inbound_check_fields = api.model(
    "InboundCheckRequest",
    {
        "text_to_match": fields.String(
            description="The input message text to match",
            required=True,
            example="is it normal to crave anchovies for breakfast",
        ),
        "metadata": fields.Raw(
            description=(
                "Can be list/dict/string/etc. Any custom metadata "
                "(inbound phone number/hash, labels, etc.). This will be "
                "stored in the inbound query database."
            ),
            required=False,
        ),
    },
)
urgency_dict = {
    "rule_id": fields.Integer(description="ID of the rule", example=1),
    "title": fields.String(description="Title of the rule ", example="Migraine"),
    "include": fields.List(fields.String()),
    "exclude": fields.List(fields.String()),
}
urgency_rule = api.model("UrgencyRule", urgency_dict)

response_dict = {
    "urgency_score": fields.Integer(
        description=(" Urgency score of message (O or 1)"),
        example=0,
    ),
    "matched_urgency_rules": fields.List(fields.Nested(urgency_rule)),
    "feedback_secret_key": fields.String(
        description=("Secret key attached to inbound query, "),
        example="feedback_secret_123",
    ),
    "inbound_id": fields.Integer(example=1234),
}

response_check_fields = api.model("InboundCheckResponseModel", response_dict)

inbound_feedback_fields = api.model(
    "InboundFeedbackRequest",
    {
        "inbound_id": fields.Integer(
            required=True,
            description="Id of the inbound message this feedback is for",
            example="1234",
        ),
        "feedback_secret_key": fields.String(
            required=True,
            description="Secret key found in response to original inbound message",
            example="feedback-secret-123",
        ),
        "feedback": fields.String(required=True),
    },
)
