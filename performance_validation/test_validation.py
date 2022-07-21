import os
from datetime import datetime

import boto3
import pandas as pd
import pytest
from nltk.corpus import stopwords
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sqlalchemy import text

from core_model.app.database_sqlalchemy import db

from .utils import S3_Handler

stopwords.ensure_loaded()


def generate_message(recall, threshold_criteria, precision, accuracy, f1, confusion):
    """Generate messages for validation results
    Warning is set to threshold criteria
    Parameters
    ----------
    result : List[dict]
        List of commit validation results
    threshold_criteria : float, 0-1
        Accuracy cut-off for warnings
    """
    current_branch = os.environ.get("BRANCH")
    repo_name = os.environ.get("REPO")
    commit = os.environ.get("HASH")
    ref = os.environ.get("REF")

    val_message = """
    [Alert] Recall was {recall} for {commit_tag} with {commit_message} on 
    branch {branch} of 
    repo {repo_name}.

    Other Indicators ->

    Precision: {precision}, 
    Accuracy: {accuracy}, 
    F1 Score: {f1}, 
    Confusion Matrix: {confusion}.
    
    """.format(
        accuracy=accuracy,
        commit_tag=commit,
        commit_message=ref,
        branch=current_branch,
        repo_name=repo_name,
        threshold_criteria=threshold_criteria,
        precision=precision,
        recall=recall,
        f1=f1,
        confusion=confusion,
    )

    message = """
        ------Model Validation Results-----
        {}
        -----------------------------------
        """.format(
        val_message
    )
    return message


def send_notification(
    content="",
    topic="arn:aws:sns:ap-south-1:678681925278:praekelt-vaccnlp-developer-notifications",
):
    """
    Function to send notification.
    """
    sns = boto3.client("sns", region_name="ap-south-1")
    sns.publish(
        TopicArn=topic,
        Message=content,
        Subject="Model Validation Results {}".format(datetime.today().date()),
    )


class TestPerformance:
    """
    Setup Class for performance validation"""

    s3 = boto3.client("s3")
    s3r = boto3.resource("s3")
    bucket = os.getenv("VALIDATION_BUCKET")

    s3_handler = S3_Handler(s3, s3r, bucket)

    insert_rule = (
        "INSERT INTO urgency_rules ("
        "urgency_rule_title, urgency_rule_tags_include, "
        "urgency_rule_tags_exclude, urgency_rule_added_utc, urgency_rule_author) "
        "VALUES (:title, :include, :exclude, :added_utc, :author)"
    )

    def get_data_to_validate(self, test_params):
        """
        Download data from S3.
        """

        prefix = test_params["DATA_PREFIX"]
        df = self.s3_handler.load_dataframe_from_object(prefix)

        return df

    def get_rules_data(self, test_params):
        """
        Download rules data from S3.
        """

        prefix = test_params["UD_RULES_PREFIX"]
        rules = self.s3_handler.load_dataframe_from_object(prefix)

        return rules

    def send_a_request_to_client(self, row, client, test_params, ud_rules):
        """
        Input a row of message data to get urgency results.
        """

        request_data = {"text_to_match": str(row[test_params["QUERY_COL"]])}
        headers = {"Authorization": "Bearer %s" % os.environ["UD_INBOUND_CHECK_TOKEN"]}

        response = dict(
            client.post("/inbound/check", json=request_data, headers=headers).get_json()
        )
        return response["urgency_score"]

    @pytest.fixture(scope="class")
    def ud_rules(self, client, db_engine, test_params):
        """
        Setup rules data in a temp db table.
        """

        self.rules_data = self.get_rules_data(test_params)

        headers = {"Authorization": "Bearer %s" % os.environ["UD_INBOUND_CHECK_TOKEN"]}

        with db_engine.connect() as db_connection:
            inbound_sql = text(self.insert_rule)
            inserts = [
                {
                    "title": row["Title"],
                    "include": eval(row["Include Tags"]),
                    "exclude": eval(row["Exclude Tags"]),
                    "added_utc": "2022-06-21",
                    "author": "Validation author",
                }
                for _, row in self.rules_data.iterrows()
            ]
            # We do a bulk insert to be more efficient
            db_connection.execute(inbound_sql, inserts)
        client.get("/internal/refresh-rules", headers=headers)
        yield
        with db_engine.connect() as db_connection:
            t = text(
                "DELETE FROM urgency_rules "
                "WHERE urgency_rule_author='Validation author'"
            )
            t2 = text("DELETE FROM mc.inbounds_ud")

            with db_connection.begin():
                db_connection.execute(t)
            with db_connection.begin():
                db_connection.execute(t2)

        client.get("/internal/refresh-rules", headers=headers)

    def test_ud_performance(self, monkeypatch, client, test_params, ud_rules):
        """
        Test the performance of UD in detecting urgent messaged.
        """

        monkeypatch.setattr(db.session, "add", lambda x: None)

        validation_df = self.get_data_to_validate(test_params)
        validation_df = validation_df.loc[
            (validation_df[test_params["TRUE_URGENCY"]].notnull())
            & (validation_df[test_params["QUERY_COL"]] != "")
        ]

        responses = [
            self.send_a_request_to_client(row, client, test_params, ud_rules)
            for _, row in validation_df.iterrows()
        ]

        predicted = pd.Series(responses)

        true_val = validation_df[test_params["TRUE_URGENCY"]]

        # Get Dummies since urgency data is coded as Yes and No
        true_val = (pd.get_dummies(true_val))["No"]
        true_val.replace({0: 1, 1: 0}, inplace=True)
        assert predicted.shape == true_val.shape

        confusion = confusion_matrix(y_true=true_val, y_pred=predicted)
        precision = precision_score(y_true=true_val, y_pred=predicted, zero_division=0)
        recall = recall_score(y_true=true_val, y_pred=predicted, zero_division=0)
        accuracy = accuracy_score(y_true=true_val, y_pred=predicted)
        f1 = f1_score(y_true=true_val, y_pred=predicted, zero_division=0)

        alert = generate_message(
            round(recall, 2),
            test_params["THRESHOLD_CRITERIA"],
            round(precision, 2),
            round(accuracy, 2),
            round(f1, 2),
            confusion,
        )
        if (recall < test_params["THRESHOLD_CRITERIA"]) & (
            os.environ.get("GITHUB_ACTIONS") is True
        ):
            send_notification(content=alert)

        else:
            print(alert)

        return recall
