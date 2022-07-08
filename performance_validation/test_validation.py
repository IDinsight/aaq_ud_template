import concurrent.futures
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

# This is required to allow multithreading to work
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
    current_branch = os.environ["BRANCH"]
    repo_name = os.environ["REPO"]
    commit = os.environ["HASH"]
    ref = os.environ["REF"]

    val_message = """
    [Alert] Recall was {recall} for {commit_tag} with {commit_message} on 
    branch {branch} of 
    repo {repo_name} 
    below threshold of {threshold_criteria}.

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

    insert_rule = (
        "INSERT INTO urgency_rules ("
        "urgency_rule_title, urgency_rule_tags_include, "
        "urgency_rule_tags_exclude, urgency_rule_added_utc, urgency_rule_author) "
        "VALUES (:title, :include, :exclude, :added_utc, :author)"
    )

    def get_data_to_validate(self):
        """
        Download data from S3.

        This can either get VALIDATION_DATA which is 2,000 rows
        and takes 2-3 hours to run or
        VALDIATION_SAMPLE which is 5 rows and takes 20 seconds.
        """

        df = pd.read_csv(os.environ["VALIDATION_DATA"])

        return df

    def get_rules_data(self):
        """
        Download rules data from S3.
        """

        rules = pd.read_csv(os.environ["VALIDATION_RULES"])

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

    @pytest.fixture
    def ud_rules(self, client, db_engine):
        """
        Setup rules data in a temp db table.
        """

        self.rules_data = self.get_rules_data()

        headers = {"Authorization": "Bearer %s" % os.environ["UD_INBOUND_CHECK_TOKEN"]}

        with db_engine.connect() as db_connection:
            inbound_sql = text(self.insert_rule)
            inserts = [
                {
                    "title": row["Title"],
                    "include": eval(row["Include Tags"]),
                    "exclude": eval(row["Exclude Tags"]),
                    "added_utc": "2022-06-21",
                    "author": "Pytest author",
                }
                for _, row in self.rules_data.iterrows()
            ]
            # We do a bulk insert to be more efficient
            db_connection.execute(inbound_sql, inserts)
        client.get("/internal/refresh-rules", headers=headers)
        yield
        with db_engine.connect() as db_connection:
            t = text(
                "DELETE FROM urgency_rules " "WHERE urgency_rule_author='Pytest author'"
            )
            db_connection.execute(t)
        client.get("/internal/refresh-rules", headers=headers)

    def test_ud_performance(self, client, test_params, ud_rules):
        """
        Test the performance of UD in detecting urgent messaged.
        """

        validation_df = self.get_data_to_validate()
        validation_df = validation_df.loc[
            (validation_df[test_params["TRUE_URGENCY"]].notnull())
            & (validation_df[test_params["QUERY_COL"]] != "")
        ]

        # we use multithreading. this is I/O bound and very inefficient if we loop
        with concurrent.futures.ThreadPoolExecutor() as executor:
            responses = executor.map(
                lambda x: self.send_a_request_to_client(
                    x, client, test_params, ud_rules
                ),
                [row for _, row in validation_df.iterrows()],
            )

        predicted = pd.Series(list(responses))

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

        if recall < test_params["THRESHOLD_CRITERIA"]:
            send_notification(
                content=generate_message(
                    recall,
                    test_params["THRESHOLD_CRITERIA"],
                    precision,
                    accuracy,
                    f1,
                    confusion,
                )
            )

        return recall
