#!make

# Load project config
include ./project_config.cfg
export

$(eval NAME=$(PROJECT_NAME))
$(eval PORT=9904)
$(eval VERSION=dev)

# Need to specify bash in order for conda activate to work.
SHELL=/bin/bash

# Note that the extra activate is needed to ensure that the activate floats env to the front of PATH
CONDA_ACTIVATE=source $$(conda info --base)/etc/profile.d/conda.sh ; conda activate ; conda activate

# env vars
APP_SECRETS = UD_INBOUND_CHECK_TOKEN ENABLE_RULE_REFRESH_CRON PROMETHEUS_MULTIPROC_DIR
DB_SECRETS = PG_ENDPOINT PG_PORT PG_USERNAME PG_PASSWORD PG_DATABASE
SENTRY_CONFIG = SENTRY_DSN SENTRY_ENVIRONMENT SENTRY_TRACES_SAMPLE_RATE

PGPASSFILE = .pgpass

# Load db details
ifneq (,./secrets/database_secrets.env)
    -include ./secrets/database_secrets.env
    export
endif

cmd-exists-%:
	@hash $(*) > /dev/null 2>&1 || \
		(echo "ERROR: '$(*)' must be installed and available on your PATH."; exit 1)
guard-%:
	@if [ -z '${${*}}' ]; then echo 'ERROR: environment variable $* not set' && exit 1; fi

setup: setup-dev setup-db-all setup-ecr

setup-db-all: setup-db init-db-tables

setup-dev: setup-env setup-secrets

setup-db: cmd-exists-psql cmd-exists-createdb guard-PG_ENDPOINT guard-PG_PORT guard-PG_USERNAME guard-PG_PASSWORD guard-PG_DATABASE
	@echo "Creating Role: $(PG_USERNAME)"
	@psql -U postgres -h $(PG_ENDPOINT) -c "CREATE ROLE $(PG_USERNAME) WITH CREATEDB LOGIN PASSWORD '$(PG_PASSWORD)';"
	@echo "Creating Role: $(PG_USERNAME)_test"
	@psql -U postgres -h $(PG_ENDPOINT) -c "CREATE ROLE $(PG_USERNAME)_test WITH CREATEDB LOGIN PASSWORD '$(PG_PASSWORD)';"
	@echo $(PG_ENDPOINT):$(PG_PORT):*:$(PG_USERNAME):$(PG_PASSWORD) > .pgpass
	@echo $(PG_ENDPOINT):$(PG_PORT):*:$(PG_USERNAME)_test:$(PG_PASSWORD) >> .pgpass
	@chmod 0600 .pgpass
	@echo "Creating Db: $(PG_DATABASE)"
	@createdb -h $(PG_ENDPOINT) -p $(PG_PORT) -U $(PG_USERNAME) -O $(PG_USERNAME) $(PG_DATABASE)
	@psql -h $(PG_ENDPOINT) -p $(PG_PORT) -U $(PG_USERNAME) -d $(PG_DATABASE) \
		-c "CREATE SCHEMA $(PROJECT_SHORT_NAME) AUTHORIZATION $(PG_USERNAME); ALTER ROLE $(PG_USERNAME) SET search_path TO $(PROJECT_SHORT_NAME);"
	@echo "Creating Db: $(PG_DATABASE)-test"
	@createdb -h $(PG_ENDPOINT) -p $(PG_PORT) -U $(PG_USERNAME)_test -O $(PG_USERNAME)_test $(PG_DATABASE)-test
	@psql -h $(PG_ENDPOINT) -p $(PG_PORT) -U $(PG_USERNAME)_test -d $(PG_DATABASE)-test \
		-c "CREATE SCHEMA $(PROJECT_SHORT_NAME) AUTHORIZATION $(PG_USERNAME)_test; ALTER ROLE $(PG_USERNAME)_test SET search_path TO $(PROJECT_SHORT_NAME);"
	@rm .pgpass

# Setup postgres tables
init-db-tables: cmd-exists-psql guard-PG_ENDPOINT guard-PG_PORT guard-PG_USERNAME guard-PG_PASSWORD guard-PG_DATABASE
	@echo $(PG_ENDPOINT):$(PG_PORT):$(PG_DATABASE):$(PG_USERNAME):$(PG_PASSWORD) > .pgpass
	@echo $(PG_ENDPOINT):$(PG_PORT):$(PG_DATABASE)-test:$(PG_USERNAME)_test:$(PG_PASSWORD) >> .pgpass
	@chmod 0600 .pgpass
	@psql -h $(PG_ENDPOINT) -U $(PG_USERNAME) -d $(PG_DATABASE) -a -f ./scripts/ud_tables.sql
	@psql -h $(PG_ENDPOINT) -U $(PG_USERNAME)_test -d $(PG_DATABASE)-test -a -f ./scripts/ud_tables.sql
	@rm .pgpass

setup-env: guard-PROJECT_CONDA_ENV cmd-exists-conda
	conda create --name $(PROJECT_CONDA_ENV) python==3.9 -y
	$(CONDA_ACTIVATE) $(PROJECT_CONDA_ENV); pip install --upgrade pip
	$(CONDA_ACTIVATE) $(PROJECT_CONDA_ENV); pip install -r requirements.txt --ignore-installed
	$(CONDA_ACTIVATE) $(PROJECT_CONDA_ENV); pip install -r requirements_dev.txt --ignore-installed
	$(CONDA_ACTIVATE) $(PROJECT_CONDA_ENV); pre-commit install

setup-secrets:
	@mkdir -p ./secrets/
	@if [ `ls -1 ./secrets | wc -l` -gt 0 ]; then \
		echo "One or more env file already exist"; exit 1; \
	fi
	@for env_var in $(APP_SECRETS) ; do \
		echo "$$env_var=" >> ./secrets/app_secrets.env ; \
	done

	@for env_var in $(DB_SECRETS) ; do \
		echo "$$env_var=" >> ./secrets/database_secrets.env ; \
	done

	@for env_var in $(SENTRY_CONFIG) ; do \
		echo "$$env_var=" >> ./secrets/sentry_config.env ; \
	done

ci:
	isort --profile black --check core_model
	black --check core_model tests
	flake8 core_model tests --count --ignore=E501,E203,E731,W503,E722 --show-source --statistics

test:
	pytest -k "not slow" tests

test-all:
	pytest tests

image:
	# Build docker image
	cp ./requirements.txt ./core_model/requirements.txt

	@docker build --rm \
		--build-arg NAME=$(NAME) \
		--build-arg PORT=$(PORT) \
		--build-arg TOKEN_MACHINE_USER=$(TOKEN_MACHINE_USER) \
		-t $(NAME):$(VERSION) \
		./core_model

	rm -rf ./core_model/requirements.txt

container:
	# Run container from image
	@docker container run \
		-p $(PORT):$(PORT) \
		--env-file ./secrets/app_secrets.env \
		--env-file ./secrets/database_secrets.env \
		--env-file ./secrets/sentry_config.env \
		$(NAME):$(VERSION)

prometheus:
	@docker container ls -a --filter name=prometheus --format "{{.ID}}" | xargs -r docker stop
	@docker container ls -a --filter name=prometheus --format "{{.ID}}" | xargs -r docker rm
	@docker container run -d \
		--name prometheus \
		-p 9091:9090 \
	    -v $(PWD)/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml \
		prom/prometheus

grafana:
	@docker container ls -a --filter name=grafana --format "{{.ID}}" | xargs -r docker stop
	@docker container ls -a --filter name=grafana --format "{{.ID}}" | xargs -r docker rm
	@docker container run -d \
		--name grafana \
		-p 3001:3000 \
	    -v $(PWD)/monitoring/grafana/datasource.yaml:/etc/grafana/provisioning/datasources/default.yaml \
		-v $(PWD)/monitoring/grafana/dashboard.yaml:/etc/grafana/provisioning/dashboards/default.yaml \
		-v $(PWD)/monitoring/grafana/dashboards:/var/lib/grafana/dashboards \
		grafana/grafana-oss
