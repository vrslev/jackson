# Dockerfile for Jackson server
FROM python:3.10-slim as jacktrip_builder

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    build-essential qtbase5-dev autoconf automake libtool make libjack-jackd2-dev git help2man \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recurse-submodules --branch v1.5.1 https://github.com/jacktrip/jacktrip \
    && cd jacktrip \
    && ./build -config nogui


FROM python:3.10-slim

RUN useradd -ms /bin/bash jackson && usermod -a -G audio jackson

USER jackson
COPY --chown=jackson poetry.lock pyproject.toml /code/
WORKDIR /code

RUN python -m venv /tmp/venv \
    && /tmp/venv/bin/pip install --no-cache-dir -U pip poetry \
    && /tmp/venv/bin/poetry export -o /tmp/requirements.txt --without-hashes \
    && python -m venv venv \
    && venv/bin/pip install --no-cache-dir -U pip \
    && venv/bin/pip install --no-cache-dir -r /tmp/requirements.txt

USER root
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    jackd2 \
    # required for JackTrip
    libqt5network5 \
    && rm -rf /var/lib/apt/lists/*

RUN echo "@audio  -  rtprio  99" | tee -a /etc/security/limits.conf \
    && echo "@audio   -  memlock    unlimited" | tee -a /etc/security/limits.conf

USER jackson


COPY --from=jacktrip_builder /jacktrip/builddir/jacktrip /usr/local/bin/

COPY . /code
RUN venv/bin/pip install --no-cache-dir .

ENTRYPOINT ["/code/venv/bin/jackson", "server"]
