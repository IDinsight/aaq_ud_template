from pathlib import Path

import pytest
import sqlalchemy
import yaml

from core_model.app import create_app, get_config_data, refresh_rule_based_model


@pytest.fixture(scope="session")
def test_params():
    with open(Path(__file__).parent / "config.yaml", "r") as stream:
        params_dict = yaml.safe_load(stream)

    return params_dict


@pytest.fixture(scope="session")
def client(test_params):
    app = create_app(test_params)
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="session")
def app_no_refresh(test_params):
    app = create_app(test_params)
    app.config["RULE_REFRESH_FREQ"] = 0
    return app


@pytest.fixture(scope="session")
def client_no_refresh(app_no_refresh):
    with app_no_refresh.test_client() as client:
        yield client


@pytest.fixture(scope="class")
def db_engine(test_params):
    config = get_config_data(test_params)
    uri = config["SQLALCHEMY_DATABASE_URI"]
    engine = sqlalchemy.create_engine(uri)
    yield engine
