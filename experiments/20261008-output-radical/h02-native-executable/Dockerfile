# Executive summary: remove interpreter startup while retaining the pinned native engine/writer.
ARG BASE_IMAGE=track3-output-base:ff2c1d6
ARG BUILDER_IMAGE=track3-output-base-builder:ff2c1d6
FROM --platform=linux/amd64 ${BUILDER_IMAGE} AS builder
COPY baselines/native /src/native
COPY baselines/build_executable.py /src/build_executable.py
RUN python /src/build_executable.py /src /native-output
FROM --platform=linux/amd64 ${BASE_IMAGE}
COPY --from=builder /native-output/t3-native /usr/local/bin/t3-native
# Keep simulate-batch and all Python fallback files unchanged.
RUN rm /usr/local/bin/simulate && ln -s /usr/local/bin/t3-native /usr/local/bin/simulate
WORKDIR /tmp
