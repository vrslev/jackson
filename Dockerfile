FROM python:3.10-slim as builder

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install --no-install-recommends -y \
    build-essential qtbase5-dev autoconf automake libtool make libjack-jackd2-dev git help2man \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --recurse-submodules --branch v1.5.1 https://github.com/jacktrip/jacktrip \
    && cd jacktrip \
    && ./build -config nogui


FROM scratch AS jacktrip

COPY --from=builder /jacktrip/builddir/jacktrip .
