# Agenthon 2026 Track 3 submission — iMak AI Lab.
#
# Pinned upstream ABIDES (jpmorganchase/abides-jpmc-public) + our `abides_fork` adapter
# providing the `simulate` / `simulate-batch` CLI verbs required by SUBMISSION_CLI.md.
#
# Baseline correctness and speed, both independently verified locally against the public
# regression suite (regression_suite/run_regression.py, 65/65 scenarios, Tier A exact +
# Tier B statistical + all 4 stylized-fact checks):
#   - unmodified upstream + patches 1-4 (organizer baseline): geomean 11,132.5 events/sec
#   - + patch 5 (debug_log_guard) + config.py get_latency fix (this image): geomean 15,541.2
#     events/sec -- +39.6%, with byte-identical trace_sha256/message_trace_sha256 on every
#     scenario (these two changes touch zero simulation logic, RNG draws, or event ordering --
#     they only stop constructing debug-log strings/arrays that were discarded immediately
#     at the configured stdout_log_level="WARNING").
#
# Deliberate exception to the org's Python 3.13 standard: ABIDES requires pandas 1.x, which
# publishes no cp313 wheels. This image is self-contained (the harness only reads the parquet
# it writes), so this does not constrain the 3.13 evaluation container.
FROM --platform=linux/amd64 python:3.11-slim

LABEL qfbench2.interface_version="2.0"

ARG ABIDES_REPO=https://github.com/jpmorganchase/abides-jpmc-public.git
ARG ABIDES_COMMIT=f9cbe51342b7dedd9587e4e069040d68a5c6477f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/opt

# Pin the exact stack that generated the reference traces.
RUN pip install \
        numpy==1.26.4 \
        pandas==1.5.3 \
        scipy==1.17.1 \
        pyarrow==15.0.2 \
        coloredlogs==15.0.1

# Fetch ABIDES at the pinned commit and apply, in order:
#   1. order_size_model.pomegranate-free.patch — drop the unbuildable pomegranate dependency.
#   2. kernel_message_ledger.patch — observation-only per-message ledger for the trace schema.
#   3. exchange_protocol_stp.patch — opt-in self-trade-prevention policy.
#   4. oracle_scheduled_jump.patch — opt-in deterministic fundamental jump.
#   5. debug_log_guard.patch — guard ~86 `logger.debug`/`logger.info` call sites (kernel.py,
#      order_book.py, trading_agent.py, exchange_agent.py) behind `isEnabledFor` so their
#      (often eager f-string/.format()) arguments stop being built and discarded on every
#      event at stdout_log_level="WARNING". Mechanically generated (AST-based), zero logic
#      change. Measured: byte-identical trace/message_trace hashes before and after.
COPY patches/ /tmp/patches/
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && git clone "${ABIDES_REPO}" /tmp/abides \
    && git -C /tmp/abides checkout "${ABIDES_COMMIT}" \
    && git -C /tmp/abides apply /tmp/patches/order_size_model.pomegranate-free.patch \
    && git -C /tmp/abides apply /tmp/patches/kernel_message_ledger.patch \
    && git -C /tmp/abides apply /tmp/patches/exchange_protocol_stp.patch \
    && git -C /tmp/abides apply /tmp/patches/oracle_scheduled_jump.patch \
    && git -C /tmp/abides apply /tmp/patches/debug_log_guard.patch \
    && pip install --no-deps /tmp/abides/abides-core /tmp/abides/abides-markets \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /tmp/abides /tmp/patches /var/lib/apt/lists/*

# Our `simulate`/`simulate-batch` adapter. `config.py` carries one additional fix beyond the
# organizer baseline: `get_latency` used `np.clip` on a plain scalar (ufunc dispatch overhead
# for a 0-d op) -- replaced with `min()/max()`, mathematically identical for a scalar, measured
# hot in cProfile (72,515 calls on the as06_throughput_fast scenario).
COPY abides_fork /opt/abides_fork
COPY simulate /usr/local/bin/simulate
COPY simulate-batch /usr/local/bin/simulate-batch
RUN chmod +x /usr/local/bin/simulate /usr/local/bin/simulate-batch

WORKDIR /work
CMD ["simulate", "--help"]
