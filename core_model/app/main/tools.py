"""
# MODEL TOOLS ENDPOINTS
"""
import os
from functools import wraps

from faqt.model.keyword_rule_matching_model import KeywordRule
from flask import abort, current_app, request

from ..prometheus_metrics import metrics
from ..src.utils import load_parameters
from . import main
from .auth import auth


def active_only_non_prod(func):
    """
    Decorator ensures route is only active in a non-prod environment
    """

    @wraps(func)
    def route(*args, **kwargs):
        """
        Abort route if env is PRODUCTION
        """
        if os.getenv("DEPLOYMENT_ENV") == "PRODUCTION":
            return abort(404)
        else:
            return func(*args, **kwargs)

    return route


@main.route("/tools/check-new-rules", methods=["POST"])
@metrics.do_not_track()
@auth.login_required
@active_only_non_prod
def check_new_rules():
    """
    Handles requests to check possible rules.
    Parameters
    ----------
    request (request proxy; see https://flask.palletsprojects.com/en/1.1.x/reqcontext/)
    The request should be sent as JSON with the following structure:

        request = {
            "include_keywords": List[str] of length up to 10 and minimum 1
            "exclude_keywords": List[str] of length up to 10
            "queries_to_check": List[str] of length up to 5
        }

    Returns
    -------
    JSON

        response = {
            "preprocessed_include_kws": List[List[str]] of length up to 10, minimum 1,
            "preprocessed_exclude_kws": List[List[str]] of length up to 10,
            "preprocessed_queries": List[List[str]] of length up to 5,
            "urgency_scores": List[float] of length up to 5, same length as "preprocessed_queries",
        }
    """
    incoming = request.json

    raw_text = incoming["queries_to_check"]
    preprocessed_text = [current_app.preprocess_text(x) for x in raw_text]

    # Preprocess keywords -- we take the last element because this is the
    # longest ngram keyword.
    include_preprocessed = [
        current_app.preprocess_text(x)[-1] for x in incoming["include_keywords"]
    ]
    exclude_preprocessed = [
        current_app.preprocess_text(x)[-1] for x in incoming["exclude_keywords"]
    ]

    rule_to_check = [
        KeywordRule(include=include_preprocessed, exclude=exclude_preprocessed)
    ]

    urgency_values = [
        current_app.evaluate_rules(x, rule_to_check) for x in preprocessed_text
    ]

    urgency_values = [item * 1 for sublist in urgency_values for item in sublist]

    json_return = dict()
    json_return["preprocessed_include_kws"] = include_preprocessed
    json_return["preprocessed_exclude_kws"] = exclude_preprocessed
    json_return["preprocessed_queries"] = preprocessed_text
    json_return["urgency_scores"] = urgency_values

    # Flask automatically calls jsonify
    return json_return


@main.route("/tools/validate-rule", methods=["POST"])
@metrics.do_not_track()
@auth.login_required
@active_only_non_prod
def validate_rules():
    """
    Validates rule. Returns list of invalid words/phrases (may be empty list)
    Parameters
    ----------
    request (request proxy; see https://flask.palletsprojects.com/en/1.1.x/reqcontext/)
        The request should be sent as JSON with fields:
        - include_keywords (required, list[str])
        - exclude_keywords (required, list[str])
    Returns
    -------
    JSON
        {
            "rule_len_test": {
                include_max: bool (True if pass),
                exclude_max: bool (True if pass)
            },
            "overlapping_include_exclude": list of rules that overlap,
            "ngram_check": list of rules that fail ngram check,
            "error": Error message if the code breaks due to stop words
        }
    """

    req_json = request.json

    ngram_specs = load_parameters("preprocessing")
    ngram_min = ngram_specs["ngram_min"]
    ngram_max = ngram_specs["ngram_max"]

    include_kw = req_json["include_keywords"]
    exclude_kw = req_json["exclude_keywords"]
    include_exclude_combined = include_kw + exclude_kw

    include_preprocessed_tokens = [current_app.preprocess_text(x) for x in include_kw]
    exclude_preprocessed_tokens = [current_app.preprocess_text(x) for x in exclude_kw]

    invalid_tags = [
        include_exclude_combined[i]
        for i, tokens in enumerate(
            include_preprocessed_tokens + exclude_preprocessed_tokens
        )
        if len(tokens) == 0
    ]
    if len(invalid_tags) > 0:
        return {
            "stopword_error": invalid_tags,
            "overlapping_include_exclude": None,
            "ngram_check": None,
            "no_errors": False,
        }

    include_preprocessed = [x[-1] for x in include_preprocessed_tokens]
    exclude_preprocessed = [x[-1] for x in exclude_preprocessed_tokens]

    overlapping_include_exclude = check_if_any_overlapping_rules(
        include_processed=include_preprocessed,
        exclude_processed=exclude_preprocessed,
    )

    rules_that_fail_ngram_test = []
    for rule in include_exclude_combined:
        result_ngram_check = check_if_rules_fit_ngram_specs(
            rule, ngram_max=ngram_max, ngram_min=ngram_min
        )
        if not result_ngram_check:
            rules_that_fail_ngram_test.append(rule)

    check_results = dict()
    check_results["no_errors"] = False
    check_results["overlapping_include_exclude"] = overlapping_include_exclude
    check_results["ngram_check"] = rules_that_fail_ngram_test
    check_results["stopword_error"] = None

    if (
        (len(check_results["overlapping_include_exclude"]) == 0)
        & (len(check_results["ngram_check"]) == 0)
        & (check_results["stopword_error"] is None)
    ):
        check_results["no_errors"] = True

    return check_results


def check_if_rules_fit_ngram_specs(rule_to_validate, ngram_min, ngram_max):
    """_summary_

    Parameters
    ----------
    rule_to_validate : str
        keyword rule
    ngram_min : int
    ngram_max : int

    Returns
    -------
    bool
    """
    if (len(rule_to_validate.split()) < ngram_min) | (
        len(rule_to_validate.split()) > ngram_max
    ):
        return False
    else:
        return True


def check_if_any_overlapping_rules(include_processed, exclude_processed):
    """Check if the same word rule is in include and exclude

    Parameters
    ----------
    include_processed : list
        preprocessed include keywords
    exclude_processed : list
        preprocessed exclude keywords

    Returns
    -------
    list
        list of words which overlap (can be an empty list)
    """
    overlap_list = list(set(include_processed) & set(exclude_processed))

    return overlap_list
