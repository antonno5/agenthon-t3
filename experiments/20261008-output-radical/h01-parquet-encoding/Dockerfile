# Executive summary: compile only H01 native sources with cached pinned Arrow15 tools.
ARG BASE_IMAGE=track3-output-base:ff2c1d6
ARG BUILDER_IMAGE=track3-output-base-builder:ff2c1d6
FROM --platform=linux/amd64 ${BUILDER_IMAGE} AS builder
COPY baselines/native /src/native
COPY baselines/build_native.py /src/native_build.py
RUN rm -f /native-output/_t3engine*.so && python /src/native_build.py /src /native-output
FROM --platform=linux/amd64 ${BASE_IMAGE}
COPY --from=builder /native-output/_t3engine*.so /opt/abides_fork/
WORKDIR /tmp
