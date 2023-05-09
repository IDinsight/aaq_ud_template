import os
from pathlib import Path

import pytest
import yaml
from sqlalchemy import text


class TestHealthCheck:
    def test_can_access_health_check(self, client):
        response = client.get("/healthcheck")
        assert response.status_code == 200

    def test_health_check_successful(self, client):
        page = client.get("/healthcheck")
        assert page.data == b"Healthy - Can connect to DB"


class TestRefresh:
    insert_rule = (
        "INSERT INTO urgency_rules ("
        "urgency_rule_tags_include, urgency_rule_tags_exclude, "
        "urgency_rule_author, urgency_rule_title, "
        "urgency_rule_added_utc) "
        "VALUES (:include, :exclude, :author, :title, "
        ":added_utc)"
    )

    ud_rule_other_params = {
        "added_utc": "2022-05-02",
        "author": "Pytest refresh",
    }

    headers = {"Authorization": "Bearer %s" % os.getenv("UD_INBOUND_CHECK_TOKEN")}

    @pytest.fixture(scope="class")
    def sample_rule_data(self):
        full_path = Path(__file__).parent / "data/urgency_rules_data.yaml"
        with open(full_path) as file:
            yaml_dict = yaml.full_load(file)
        return yaml_dict["rule_refresh_data"]

    @pytest.fixture
    def load_rule_data(self, client, db_engine, sample_rule_data):

        with db_engine.connect() as db_connection:
            inbound_sql = text(self.insert_rule)
            for i, sample_data in enumerate(sample_rule_data):
                db_connection.execute(
                    inbound_sql,
                    **sample_data,
                    **self.ud_rule_other_params,
                )
        yield
        with db_engine.connect() as db_connection:
            t = text(
                "DELETE FROM urgency_rules "
                "WHERE urgency_rule_author='Pytest refresh'"
            )
            db_connection.execute(t)
        client.get("/internal/refresh-rules", headers=self.headers)

    def test_refresh_of_four_rules(self, load_rule_data, client_no_refresh, db_engine):
        response = client_no_refresh.get(
            "/internal/refresh-rules", headers=self.headers
        )
        assert response.status_code == 200
        assert response.get_data() == b"Successfully refreshed 4 urgency rules"

    def test_refresh_of_zero_rules(self, client_no_refresh, db_engine):
        response = client_no_refresh.get(
            "/internal/refresh-rules", headers=self.headers
        )
        assert response.status_code == 200
        assert (
            response.get_data()
            == b"Successfully refreshed but could not find urgency rules in DB"
        )
