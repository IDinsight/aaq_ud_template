import os

import pytest
from sqlalchemy import text


class TestInboundMessage:
    insert_rule = (
        "INSERT INTO urgency_rules ("
        "urgency_rule_tags_include, urgency_rule_tags_exclude, "
        "urgency_rule_author, urgency_rule_title, "
        "urgency_rule_added_utc) "
        "VALUES (:rule_include, :rule_exclude, :author, :title, "
        ":added_utc)"
    )
    ud_rules = [  # (title, include, exclude)
        ("music", """{"rock", "guitar", "melodi"}""", """{}"""),
        ("guitar_hike", """{"guitar", "hike"}""", """{"melodi"}"""),
        ("hiking", """{"rock", "lake", "hike"}""", """{}"""),
        ("no_love", """{}""", """{"love"}"""),
    ]
    ud_rule_other_params = {
        "added_utc": "2022-05-02",
        "author": "Pytest author",
        "content": "{}",
    }
    headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

    @pytest.fixture
    def ud_rule_data(self, client, db_engine):
        with db_engine.connect() as db_connection:
            inbound_sql = text(self.insert_rule)
            for i, rule_info in enumerate(self.ud_rules):
                db_connection.execute(
                    inbound_sql,
                    title=rule_info[0],
                    rule_include=rule_info[1],
                    rule_exclude=rule_info[2],
                    **self.ud_rule_other_params,
                )
        client.get("/internal/refresh-rules", headers=self.headers)
        yield
        with db_engine.connect() as db_connection:
            t = text(
                "DELETE FROM urgency_rules " "WHERE urgency_rule_author='Pytest author'"
            )
            db_connection.execute(t)
        client.get("/internal/refresh-rules", headers=self.headers)

    @pytest.mark.parametrize(
        "message, expected_matched_rule_titles",
        [
            ("I love going hiking or rock climbing in the lake", {"hiking"}),
            (
                "I love rocking a melody on my guitar by the lake after a hike",
                {"music", "hiking"},
            ),
            ("I like to hike rocks by the lake", {"hiking", "no_love"}),
            ("I love the melody of the guitar", set()),
        ],
    )
    def test_inbound_returns_correct_list_of_matched_ruels(
        self, client, ud_rule_data, message, expected_matched_rule_titles
    ):
        request_data = {
            "text_to_match": message,
        }
        response = client.post(
            "/inbound/check", json=request_data, headers=self.headers
        )
        json_data = response.get_json()

        matched_rule_titles = {x["title"] for x in json_data["matched_urgency_rules"]}
        assert matched_rule_titles == expected_matched_rule_titles

    def test_inbound_endpoint_works(self, client, ud_rule_data):
        request_data = {
            "text_to_match": """ I'm worried about the vaccines. Can I have some
        information? \U0001f600
        πλέων ἐπὶ οἴνοπα πόντον ἐπ᾽ ἀλλοθρόους ἀνθρώπους, ἐς Τεμέσην""",
        }
        response = client.post(
            "/inbound/check", json=request_data, headers=self.headers
        )
        json_data = response.get_json()
        assert "inbound_id" in json_data
        assert "urgency_score" in json_data
        assert "matched_urgency_rules" in json_data
        assert "feedback_secret_key" in json_data

    def test_inbound_endpoint_works_with_no_rules(self, client):
        request_data = {
            "text_to_match": """ I'm worried about the vaccines. Can I have some
        information? \U0001f600
        πλέων ἐπὶ οἴνοπα πόντον ἐπ᾽ ἀλλοθρόους ἀνθρώπους, ἐς Τεμέσην""",
        }
        response = client.post(
            "/inbound/check", json=request_data, headers=self.headers
        )
        json_data = response.get_json()
        assert json_data["urgency_score"] is None
        assert len(json_data["matched_urgency_rules"]) == 0


@pytest.mark.slow
class TestInboundFeedback:
    headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

    insert_inbound = (
        "INSERT INTO inbounds_ud ("
        "inbound_text, feedback_secret_key, inbound_metadata, "
        "inbound_utc, urgency_score, returned_content, returned_utc) "
        "VALUES ('i am 12. Can i get the vaccine?', :secret_key, :metadata, "
        ":utc, :score, :content, :r_utc)"
    )
    inbound_other_params = {
        "secret_key": "abc123",
        "metadata": "{}",
        "utc": "2022-05-02",
        "score": "{}",
        "content": "{}",
        "r_utc": "2022-05-02",
    }

    @pytest.fixture(scope="class")
    def inbounds(self, db_engine):
        with db_engine.connect() as db_connection:
            inbound_sql = text(self.insert_inbound)
            db_connection.execute(inbound_sql, **self.inbound_other_params)

        yield
        with db_engine.connect() as db_connection:
            t = text("DELETE FROM inbounds_ud")
            db_connection.execute(t)

    @pytest.fixture(scope="class")
    def inbound_id(self, inbounds, db_engine):
        with db_engine.connect() as db_connection:
            get_inbound_id_sql = text("SELECT MAX(inbound_id) FROM " "inbounds_ud")
            results = db_connection.execute(get_inbound_id_sql)
            inbound_id = next(results)["max"]

        yield inbound_id

    def test_inbound_feedback_nonexistent_id(self, client):
        request_data = {"inbound_id": 0, "feedback_secret_key": "abcde", "feedback": ""}

        response = client.put(
            "/inbound/feedback", json=request_data, headers=self.headers
        )
        assert response.status_code == 404
        assert response.data == b"No Matches"

    def test_inbound_feedback_wrong_feedback_key(self, inbound_id, client):
        request_data = {
            "inbound_id": inbound_id,
            "feedback_secret_key": "wrong_secret_key",
            "feedback": "",
        }
        response = client.put(
            "/inbound/feedback", json=request_data, headers=self.headers
        )
        assert response.status_code == 403
        assert response.data == b"Incorrect Feedback Secret Key"

    def test_inbound_feedback_success(self, inbounds, inbound_id, client):
        request_data = {
            "inbound_id": inbound_id,
            "feedback_secret_key": "abc123",
            "feedback": "test_feedback",
        }

        response = client.put(
            "/inbound/feedback", json=request_data, headers=self.headers
        )
        assert response.status_code == 200
        assert response.data == b"Success"
