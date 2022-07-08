from pathlib import Path

import pytest
import sqlalchemy
import yaml

from core_model.app import create_app, get_config_data


@pytest.fixture(scope="session")
def test_params():
    """Create test params fixture"""
    with open(Path(__file__).parent / "config.yaml", "r") as stream:
        params_dict = yaml.safe_load(stream)

    return params_dict


@pytest.fixture(scope="session")
def client(test_params):
    """Create Flask client fixture"""
    app = create_app(test_params)
    with app.test_client() as client:
        yield client


@pytest.fixture(scope="class")
def db_engine(test_params):
    """Create DB engine fixture"""
    config = get_config_data(test_params)
    uri = config["SQLALCHEMY_DATABASE_URI"]
    engine = sqlalchemy.create_engine(uri, pool_recycle=600)
    yield engine
