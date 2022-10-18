# DESCRIPTION: Dockerfile for aaq_ud_template (AAQ Urgency Detection)
# BUILD: "make image" or "make image NAME={PROJECT_NAME} PORT={PORT}"

FROM praekeltfoundation/python-base:3.9.6
LABEL maintainer="IDinsight"

ARG NAME
ARG PORT
ARG TOKEN_MACHINE_USER
ARG HOME_DIR=/usr/src/${NAME}

# Install psycopg2 dependencies
# This is the proper way to do it; psycopg2-binary (Python package
# that doesn't rely on dependencies) is practical for development
# and testing but not suitable for production
RUN apt-get-install.sh python3-dev \
    postgresql postgresql-contrib python3-psycopg2 \
    libpq-dev gcc g++ cron curl git

COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt
RUN pip install "git+https://${TOKEN_MACHINE_USER}@github.com/IDinsight/faqt.git@v1.0.0-rc"

RUN useradd -ms /bin/bash -d ${HOME_DIR} container_user
RUN chown -R container_user: ${HOME_DIR}

RUN mkdir /tmp/prometheus
RUN chown -R container_user: /tmp/prometheus

ENV PYTHONPATH "${PYTHONPATH}:${HOME_DIR}"
ENV PORT ${PORT}

RUN python3 -m nltk.downloader stopwords punkt -d ${HOME_DIR}/nltk_data

COPY . ${HOME_DIR}
WORKDIR ${HOME_DIR}
RUN ["chmod", "+x", "startup.sh"]

EXPOSE ${PORT}

# Note that we don't switch to container_user here
# Rather, it's done when starting gunicorn with su-exec;
# see startup.sh for more details

CMD ["./startup.sh"]
