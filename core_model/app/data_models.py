from .database_sqlalchemy import db


class Inbound(db.Model):
    """
    SQLAlchemy data model for Inbound API calls (with model and return metadata)
    """

    __tablename__ = "inbounds_ud"

    inbound_id = db.Column(db.Integer(), primary_key=True)
    inbound_text = db.Column(db.String())
    inbound_metadata = db.Column(db.JSON())
    inbound_utc = db.Column(db.DateTime())

    urgency_score = db.Column(db.JSON())

    returned_content = db.Column(db.JSON())
    returned_utc = db.Column(db.DateTime())
    returned_feedback = db.Column(db.JSON())
    feedback_secret_key = db.Column(db.String())

    def __repr__(self):
        """repr string"""
        return "<Inbound %r>" % self.inbound_id


class RulesModel(db.Model):
    """
    SQLAlchemy data model for rules
    """

    __tablename__ = "urgency_rules"

    urgency_rule_id = db.Column(db.Integer, primary_key=True)
    urgency_rule_added_utc = db.Column(db.DateTime())
    urgency_rule_author = db.Column(db.String())
    urgency_rule_title = db.Column(db.String())
    urgency_rule_tags_include = db.Column(db.ARRAY(db.String()))
    urgency_rule_tags_exclude = db.Column(db.ARRAY(db.String()))

    def __repr__(self):
        """repr string"""
        return "<UrgencyRule %r>" % self.urgency_rule_id


class TemporaryModel:
    """
    Custom class to use for temporary models. Used as a drop in for other
    db.Model classes. Useful when we don't want to create a record in the Db
    (e.g. checking new tags)
    """

    def __init__(self, **kwargs):
        """init"""
        self.__dict__.update(kwargs)
