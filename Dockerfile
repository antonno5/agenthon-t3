# Track 3 baseline image: pinned upstream ABIDES + the `abides_fork` simulate adapter.
#
# This is the pre-built baseline the organizers ship. ABIDES itself is NOT vendored
# in this repo; it is fetched at build time at the pinned commit (see README.md) and
# the `abides_fork` adapter (this directory) layers the canonical `simulate` verb on
# top of the patched Python engine and the supported native simulation path.
#
# Build context is the team repository root. Build for the evaluation platform:
#
#   docker build --platform=linux/amd64 -t agenthon-t3:local .
#
# The evaluation harness (regression_suite/run_regression.py) runs it, network
# disabled, exactly as a participant submission would be run:
#
#   docker run --rm --network none \
#       -v <in>:/input:ro -v <out>:/output \
#       track3-abides-baseline:latest \
#       simulate --config /input/scenario.json --out /output/trace.parquet
# NOTE — deliberate exception to the org's Python 3.13 standard. Do NOT bump this.
# ABIDES requires pandas 1.x, and the pinned stack below (numpy==1.26.4, pandas==1.5.3) publishes
# no cp313 wheels; this is also the exact stack that generated the frozen reference traces. The
# image is self-contained (the harness only reads the parquet it writes), so it does not constrain
# the 3.13 evaluation container or participant submission images.
FROM --platform=linux/amd64 python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce AS python_base

# Required on every submission image by the published contract (SUBMISSION_CLI.md and the
# CodaBench Submission Format page). The reference baseline satisfies the same rule it asks
# participants to follow.
LABEL qfbench2.interface_version="2.0"

# ABIDES is pinned to the canonical Track 3 baseline commit (see baselines/README.md).
# Override at build time only to test a different upstream pin.
ARG ABIDES_REPO=https://github.com/jpmorganchase/abides-jpmc-public.git
ARG ABIDES_COMMIT=f9cbe51342b7dedd9587e4e069040d68a5c6477f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt

# Pin the exact stack that generated the reference traces. ABIDES needs pandas 1.x;
# the eval container's pandas 2.x is irrelevant because this image is self-contained
# and the harness only *reads* the parquet it writes. coloredlogs is a runtime import
# of abides_core.abides (it is NOT declared in ABIDES's setup.cfg, so the --no-deps
# install below will not pull it — it must be installed explicitly here).
RUN pip install \
        numpy==1.26.4 \
        pandas==1.5.3 \
        scipy==1.17.1 \
        pyarrow==15.0.2 \
        coloredlogs==15.0.1 \
        humanfriendly==10.0 \
        packaging==26.3 \
        python-dateutil==2.9.0.post0 \
        pytz==2026.5 \
        six==1.17.0 \
        pip==24.0 \
        setuptools==79.0.1 \
        wheel==0.46.3

# Fetch ABIDES at the pinned commit and apply our build-time overlays from patches/ to a
# FRESH upstream clone (upstream repo untouched; nothing modified is committed anywhere):
#   1. order_size_model.pomegranate-free.patch — drop the unbuildable pomegranate dependency
#      (drop-in NumPy mixture sampler).
#   2. kernel_message_ledger.patch — observation-only instrumentation that surfaces per-message
#      send/recv/latency/causal_parent/seq metadata in end_state for the v2 enriched trace
#      schema. Zero extra RNG; no simulation-logic, ordering, or RNG change.
#   3. exchange_protocol_stp.patch — adds an OPT-IN self-trade-prevention policy to the exchange
#      (ExchangeAgent.stp_policy, default None = legacy behavior; OrderBook honors cancel_newest /
#      cancel_oldest). Inert unless a scenario opts in, so all existing references are unchanged.
#   4. oracle_scheduled_jump.patch — adds an OPT-IN deterministic fundamental jump (reactive-agent
#      intervention) to SparseMeanRevertingOracle. RNG-neutral; absent -> legacy, refs unchanged.
#   5. dropout_python_control.patch — scan book history directly for liquidity-gap metrics,
#      preserving exact integer arithmetic and the original open trailing-gap behavior.
#   6. debug_logging.patch — skip eager DEBUG argument formatting when DEBUG is disabled;
#      preserve message text and callback behavior when DEBUG is enabled.
#   7. lazy_distance_import.patch — load SciPy distance routines only for the optional
#      line-distance latency model, preserving explicit and wildcard utility exports.
# git is installed and removed inside one layer so it does not bloat the image.
COPY patches/ /tmp/patches/
COPY matching/ /tmp/book-layers/matching/
COPY matching_compat/ /tmp/book-layers/matching_compat/
COPY install_matching.py /tmp/book-layers/install_matching.py
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git clone "${ABIDES_REPO}" /tmp/abides \
    && git -C /tmp/abides checkout "${ABIDES_COMMIT}" \
    && git -C /tmp/abides apply /tmp/patches/order_size_model.pomegranate-free.patch \
    && git -C /tmp/abides apply /tmp/patches/kernel_message_ledger.patch \
    && git -C /tmp/abides apply /tmp/patches/exchange_protocol_stp.patch \
    && git -C /tmp/abides apply /tmp/patches/oracle_scheduled_jump.patch \
    && git -C /tmp/abides apply /tmp/patches/dropout_python_control.patch \
    && git -C /tmp/abides apply /tmp/patches/debug_logging.patch \
    && git -C /tmp/abides apply /tmp/patches/lazy_distance_import.patch \
    && python /tmp/book-layers/install_matching.py /tmp/abides/abides-markets/abides_markets \
    && pip install --no-deps /tmp/abides/abides-core /tmp/abides/abides-markets \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /tmp/abides /tmp/patches /tmp/book-layers /var/lib/apt/lists/*

# Retain the upstream redistribution notice for the extracted Python book code.
COPY matching/LICENSE.abides /opt/licenses/abides-matching-LICENSE

# The Track 3 `simulate` adapter (component-1 classical baseline) and its CLI shims. `simulate` is the
# single-scenario verb; `simulate-batch` is the batched multi-scenario verb (BatchMarketSim / family GB):
# it runs N sub-scenarios in one process and writes one output subdir each + batch_events.json.
COPY abides_fork /opt/abides_fork
COPY _abides_python_control.py /opt/_abides_python_control.py
COPY simulate /usr/local/bin/simulate
COPY simulate-batch /usr/local/bin/simulate-batch
RUN chmod +x /usr/local/bin/simulate /usr/local/bin/simulate-batch

# ABIDES writes its summary log under ./log even with per-agent logging disabled.
# The platform makes the root filesystem read-only and provides a writable /tmp.
WORKDIR /tmp
# Build tools stay in the builder; the runtime retains the optimized Python fallback.
FROM python_base AS native_build
RUN apt-get update && apt-get install -y --no-install-recommends g++ gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
COPY native /src/native
COPY build_native.py /src/native_build.py
COPY build_executable.py /src/build_executable.py
RUN mkdir /native-output && python /src/native_build.py /src /native-output \
    && python /src/build_executable.py /src /native-output

FROM python_base AS runtime
COPY --from=native_build /native-output/_t3engine*.so /opt/abides_fork/
COPY --from=native_build /native-output/t3-native /usr/local/bin/t3-native
COPY native /opt/native-source
COPY build_native.py /opt/native_build.py
COPY build_executable.py /opt/build_executable.py
COPY native/LICENSE.abides /opt/licenses/native-abides-LICENSE
COPY native/svml/LICENSE /opt/licenses/native-numpy-LICENSE
COPY native/vendor/LICENSE.json /opt/licenses/native-json-LICENSE
# Both verbs run the native executable; it hands anything it cannot run (and `simulate-batch`
# batches containing such a sub) to the original Python adapters.
RUN rm /usr/local/bin/simulate /usr/local/bin/simulate-batch \
    && ln -s /usr/local/bin/t3-native /usr/local/bin/simulate \
    && ln -s /usr/local/bin/t3-native /usr/local/bin/simulate-batch
# Drop what no run path imports: package test suites, pip/setuptools/wheel, pyarrow headers and
# its Flight/Substrait libraries (pyarrow dataset/acero stay: the Python adapter's
# pandas.to_parquet needs them). Every container start reads less from disk.
RUN SP=/usr/local/lib/python3.11/site-packages \
    && find "$SP" -depth -type d \( -name tests -o -name test \) -exec rm -rf {} + \
    && rm -rf "$SP"/pip "$SP"/pip-* "$SP"/setuptools "$SP"/setuptools-* "$SP"/wheel "$SP"/wheel-* \
              "$SP"/_distutils_hack "$SP"/distutils-precedence.pth "$SP"/pyarrow/include \
              "$SP"/pyarrow/libarrow_flight.so* "$SP"/pyarrow/libarrow_substrait.so* \
              "$SP"/pyarrow/_flight* "$SP"/pyarrow/_substrait* "$SP"/pyarrow/libarrow_python_flight.so \
              /usr/local/bin/pip* /usr/local/bin/wheel /usr/local/bin/idle* /usr/local/bin/pydoc*
RUN python -m compileall -q -j 0 /usr/local/lib/python3.11 /opt
ENV T3_ENGINE=auto
WORKDIR /tmp
# No ENTRYPOINT: the harness passes `simulate --config ... --out ...` as the command.
CMD ["simulate", "--help"]

# ---------------------------------------------------------------------------------------------
# Published image: the runtime file system flattened into ONE layer (one overlay lower dir to
# mount per container start instead of ~15), with the runtime stage's config re-declared
# verbatim (same Env order, WorkingDir, Cmd, label).
# ---------------------------------------------------------------------------------------------
FROM scratch
COPY --from=runtime / /
LABEL qfbench2.interface_version="2.0"
ENV PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin \
    LANG=C.UTF-8 \
    GPG_KEY=A035C8C19219BA821ECEA86B64E628F8D684696D \
    PYTHON_VERSION=3.11.17 \
    PYTHON_SHA256=bfb74ad39efae27cda510f134ab408e00f9992c56851cfc0b1cdb5646da11599 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt \
    T3_ENGINE=auto
WORKDIR /tmp
CMD ["simulate", "--help"]
