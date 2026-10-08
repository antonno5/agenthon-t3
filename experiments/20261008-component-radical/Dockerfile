# Executive summary: build isolated native candidates with the audited cached compiler and pinned runtime.
ARG BASE_IMAGE=track3-ledger-arena:286ae97
ARG BUILDER_IMAGE=track3-ledger-arena-builder:286ae97
FROM --platform=linux/amd64 ${BUILDER_IMAGE} AS builder
COPY baselines/native /src/native
COPY baselines/build_native.py /src/native_build.py
RUN rm -f /native-output/_t3engine*.so && python /src/native_build.py /src /native-output
FROM --platform=linux/amd64 ${BASE_IMAGE}
COPY --from=builder /native-output/_t3engine*.so /opt/abides_fork/
WORKDIR /tmp
