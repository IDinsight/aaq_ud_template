"""
Create and initialise the app. Uses Blueprints to define view.
"""
import os
import time
from functools import lru_cache, partial

from faqt import KeywordRule, preprocess_text_for_keyword_rule
from faqt.model.urgency_detection.urgency_detection_base import RuleBasedUD
from faqt.preprocessing.tokens import CustomHunspell
from flask import Flask
from nltk.stem import PorterStemmer

from .data_models import RulesModel
from .database_sqlalchemy import db
from .prometheus_metrics import metrics
from .src.utils import DefaultEnvDict, get_postgres_uri, load_parameters


def create_app(params=None):
    """
    Factory to create a new flask app instance
    """
    app = Flask(__name__)
    setup(app, params)

    from .main import main as main_blueprint

    app.register_blueprint(main_blueprint)
    return app


def setup(app, params):
    """
    Add config to app and initialise extensions.

    Parameters
    ----------
    app : Flask app
        A newly created flask app
    params : Dict
        A dictionary with config parameters
    """

    if params is None:
        params = {}

    config = get_config_data(params)

    app.config.from_mapping(
        JSON_SORT_KEYS=False,
        SECRET_KEY=os.urandom(24),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={
            "pool_pre_ping": True,
            "pool_recycle": 300,
        },
        **config,
    )

    db.init_app(app)
    metrics.init_app(app)

    app.preprocess_text = get_text_preprocessor()

    app.cached_rule_based_model_func = cached_rules_wrapper(app)


def get_config_data(params):
    """
    If parameter exists in `params` use that else use env variables.
    """

    config = DefaultEnvDict()
    config.update(params)

    config["SQLALCHEMY_DATABASE_URI"] = get_postgres_uri(
        config["PG_ENDPOINT"],
        config["PG_PORT"],
        config["PG_DATABASE"],
        config["PG_USERNAME"],
        config["PG_PASSWORD"],
    )

    return config


def get_text_preprocessor():
    """
    Return a partial function that takes one argument - the raw function
    to be processed.
    """

    pp_params = load_parameters("preprocessing")
    n_min_dashed_words_url = pp_params["min_dashed_words_to_parse_text_from_url"]
    reincluded_stop_words = pp_params["reincluded_stop_words"]
    ngram_min = pp_params["ngram_min"]
    ngram_max = pp_params["ngram_max"]
    custom_spell_check_list = pp_params["custom_spell_check_list"]
    custom_spell_correct_map = pp_params["custom_spell_correct_map"]
    priority_words = pp_params["priority_words"]

    custom_spell_checker = CustomHunspell(
        custom_spell_check_list=custom_spell_check_list,
        custom_spell_correct_map=custom_spell_correct_map,
        priority_words=priority_words,
    )

    text_preprocessor = partial(
        preprocess_text_for_keyword_rule,
        n_min_dashed_words_url=n_min_dashed_words_url,
        reincluded_stop_words=reincluded_stop_words,
        stem_func=PorterStemmer().stem,
        spell_checker=custom_spell_checker,
        ngram_min=ngram_min,
        ngram_max=ngram_max,
    )

    return text_preprocessor


def refresh_rules(app):
    """
    Queries DB for rules, and attaches to app.rules for urgency detection
    """

    # Need to push application context. Otherwise will raise:
    # RuntimeError: No application found.
    # Either work inside a view function or push an application context.
    # See http://flask-sqlalchemy.pocoo.org/contexts/.

    with app.app_context():
        rows = RulesModel.query.all()
    rows.sort(key=lambda x: x.urgency_rule_id)

    rules = [
        {
            "rule_id": x.urgency_rule_id,
            "title": x.urgency_rule_title,
            "rule": KeywordRule(
                include=[s.lower() for s in x.urgency_rule_tags_include],
                exclude=[s.lower() for s in x.urgency_rule_tags_exclude],
            ),
        }
        for x in rows
    ]
    app.rules = rules
    return rules


def refresh_rule_based_model(app):
    """Add new rules to RuleBasedUD  evaluator"""
    rules_data = refresh_rules(app)
    rules = [rule["rule"] for rule in rules_data]
    app.evaluator = RuleBasedUD(model=rules, preprocessor=app.preprocess_text)
    return len(rules)


def cached_rules_wrapper(app):
    """Wrapper to cached rule based model"""

    @lru_cache(maxsize=1)
    def cached_rules(ttl_hash):
        """
        Caches `refresh_rule_based_model` results
        """
        n_rules = refresh_rule_based_model(app)
        return n_rules

    return cached_rules


def get_ttl_hash(seconds=3600):
    """Return the same value within `seconds` time period"""
    return time.time() // seconds


def refresh_rule_based_model_cached(app):
    """Add new rules to RuleBasedUD  evaluator"""

    return app.cached_rule_based_model_func(ttl_hash=get_ttl_hash())
