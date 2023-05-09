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
APP_SECRETS = UD_INBOUND_CHECK_TOKEN ENABLE_RULE_REFRESH_CRON PROMETHEUS_MULTIPROC_DIR RULE_REFRESH_FREQ
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

setup: setup-dev setup-db-tables setup-ecr

setup-db-tables: check-db init-db-tables

setup-dev: setup-env setup-secrets

check-db: cmd-exists-psql guard-PG_ENDPOINT guard-PG_PORT guard-PG_PASSWORD guard-PG_DATABASE
	@read -s -p "Enter master 'postgres' password: " PGPASSWORD; \
	echo $(PG_ENDPOINT):$(PG_PORT):*:postgres:$$PGPASSWORD > .pgpass
	@chmod 0600 .pgpass

	@echo ""
	@echo "Checking if role $(PG_USERNAME) exists..." 
	@result=`psql -U postgres -h $(PG_ENDPOINT) -tAc "SELECT 1 FROM pg_roles WHERE rolname='$(PG_USERNAME)'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: role $(PG_USERNAME) does not exist.' && exit 1; fi

	@echo "Checking if role $(PG_USERNAME)_test exists..."
	@result=`psql -U postgres -h $(PG_ENDPOINT) -tAc "SELECT 1 FROM pg_roles WHERE rolname='$(PG_USERNAME)_test'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: role $(PG_USERNAME)_test does not exist.' && exit 1; fi

	@echo "Checking if database $(PG_DATABASE) exists..."
	@result=`psql -U postgres -h $(PG_ENDPOINT) -p $(PG_PORT) -XtAc "SELECT 1 FROM pg_database WHERE datname='$(PG_DATABASE)'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: database $(PG_DATABASE) does not exist.' && exit 1; fi

	@echo "Checking if owner of database $(PG_DATABASE) is $(PG_USERNAME)..."
	@result=`psql -U postgres -h $(PG_ENDPOINT) -p $(PG_PORT) -XtAc "SELECT 1 FROM pg_database, pg_roles WHERE pg_database.datname = '$(PG_DATABASE)' AND pg_database.datdba = pg_roles.oid AND pg_roles.rolname = '$(PG_USERNAME)'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: owner of database $(PG_DATABASE) is not $(PG_USERNAME).' && exit 1; fi

	@echo "Checking if database $(PG_DATABASE)-test exists..."
	@result=`psql -U postgres -h $(PG_ENDPOINT) -p $(PG_PORT) -XtAc "SELECT 1 FROM pg_database WHERE datname='$(PG_DATABASE)-test'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: database $(PG_DATABASE)-test does not exist.' && exit 1; fi

	@echo "Checking if owner of database $(PG_DATABASE)-test is $(PG_USERNAME)_test..."
	@result=`psql -U postgres -h $(PG_ENDPOINT) -p $(PG_PORT) -XtAc "SELECT 1 FROM pg_database, pg_roles WHERE pg_database.datname='$(PG_DATABASE)-test' AND pg_database.datdba=pg_roles.oid AND pg_roles.rolname='$(PG_USERNAME)_test'"`; \
	if [[ $$result != "1" ]]; then echo 'ERROR: owner of database $(PG_DATABASE)-test is not $(PG_USERNAME)_test.' && exit 1; fi

	@echo "All checks passed."
	@rm .pgpass

setup-ecr: cmd-exists-aws
	aws ecr create-repository \
		--repository-name aaq_solution/$(NAME) \
		--region af-south-1

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

push-image: image cmd-exists-aws
	aws ecr --profile=praekelt-user get-login-password --region af-south-1 \
		| docker login --username AWS --password-stdin $(AWS_ACCOUNT_ID).dkr.ecr.af-south-1.amazonaws.com
	docker tag $(NAME):$(VERSION) $(AWS_ACCOUNT_ID).dkr.ecr.af-south-1.amazonaws.com/aaq_solution/$(NAME):$(VERSION)
	docker push $(AWS_ACCOUNT_ID).dkr.ecr.af-south-1.amazonaws.com/aaq_solution/$(NAME):$(VERSION)

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

container-stg:
	# Configure ecs-cli options
	@ecs-cli configure --cluster ${PROJECT_SHORT_NAME}-cluster \
	--default-launch-type EC2 \
	--region $(AWS_REGION) \
	--config-name ${NAME}-config

	@PROJECT_NAME=$(NAME) \
	PORT=$(PORT) \
	IMAGE_NAME=$(AWS_ACCOUNT_ID).dkr.ecr.af-south-1.amazonaws.com/aaq_solution/$(NAME):$(VERSION) \
	AWS_REGION=$(AWS_REGION) \
	ecs-cli compose -f docker-compose/docker-compose-stg.yml \
	--project-name ${NAME} \
	--cluster-config ${NAME}-config \
	--task-role-arn arn:aws:iam::$(AWS_ACCOUNT_ID):role/${PROJECT_SHORT_NAME}-task-role \
	service up \
	--create-log-groups \
	--deployment-min-healthy-percent 0 

down-stg:
	@ecs-cli compose \
	-f docker-compose/docker-compose-stg.yml \
	--project-name ${NAME} \
	--cluster-config ${NAME}-config service down