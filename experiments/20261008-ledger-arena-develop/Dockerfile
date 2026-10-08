# Executive summary: compile combined sources against the unchanged pinned runtime.
ARG BASE_IMAGE=track3-radical-base:a7fb6c3
FROM --platform=linux/amd64 ${BASE_IMAGE} AS builder
RUN apt-get update && apt-get install -y --no-install-recommends g++ gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY baselines/native /src/native
COPY baselines/build_native.py /src/native_build.py
COPY expirements/20261008-ledger-arena-develop/tests /src/h02-tests
RUN mkdir /native-output && python /src/native_build.py /src /native-output \
    && g++ -std=c++17 -O2 -Wall -pthread -I/src/native /src/native/tests/book_test.cpp -o /native-output/book_test \
    && /native-output/book_test \
    && python /src/h02-tests/build_checks.py
FROM --platform=linux/amd64 ${BASE_IMAGE}
COPY --from=builder /native-output/_t3engine*.so /opt/abides_fork/
WORKDIR /tmp
