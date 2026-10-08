# Executive summary: native lifecycle candidate on the frozen cached Arrow15 runtime/toolchain.
ARG BASE_IMAGE=track3-output-base:ff2c1d6
ARG BUILDER_IMAGE=track3-output-base-builder:ff2c1d6
FROM --platform=linux/amd64 ${BUILDER_IMAGE} AS builder
COPY baselines/native /src/native
COPY baselines/build_native.py /src/native_build.py
COPY experiments/20261008-output-radical/h04-lifecycle-pipeline/tests /src/h04-tests
RUN rm -f /native-output/_t3engine*.so && python /src/native_build.py /src /native-output \
    && python /src/h04-tests/run_checks.py --pinned --source /src/native --out /native-output/h04-checks \
    && python /src/h04-tests/audit_build.py
FROM --platform=linux/amd64 ${BASE_IMAGE}
RUN mkdir /opt/h04-reference && cp /opt/abides_fork/_t3engine*.so /opt/h04-reference/
COPY --from=builder /native-output/_t3engine*.so /opt/abides_fork/
COPY --from=builder /native-output/h04-checks/summary.json /opt/h04-checks/synthetic-summary.json
COPY --from=builder /native-output/h04-checks/native-build-audit.json /opt/h04-checks/
COPY experiments/20261008-output-radical/h04-lifecycle-pipeline/tests /opt/h04-tests
WORKDIR /tmp
