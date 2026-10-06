# Agenthon 2026 Track 3 submission — iMak AI Lab.
#
# Pinned upstream ABIDES (jpmorganchase/abides-jpmc-public) + our `abides_fork` adapter
# providing the `simulate` / `simulate-batch` CLI verbs required by SUBMISSION_CLI.md.
#
# Baseline correctness and speed, both independently verified locally against the public
# regression suite (regression_suite/run_regression.py, 65/65 scenarios, Tier A exact +
# Tier B statistical + all 4 stylized-fact checks), on every revision below:
#   - unmodified upstream + patches 1-4 (organizer baseline):            geomean 11,132.5 events/sec
#   - + patch 5 (debug_log_guard) + config.py get_latency fix:           geomean 15,541.2 ev/s (+39.6%)
#   - + config.py Agent.logEvent fast path:                             geomean 17,064.8 ev/s (+53.3%)
#   - + patch 6 (heapq kernel queue, tuple message ledger), order snapshots instead of
#     Order.to_dict, no book_log2, columnar trace extraction, Cython-compiled modules
#     (this image). All 65 public units byte-identical (trace + message_trace sha256).
# All three changes touch zero simulation logic, RNG draws, or event ordering -- each was
# verified byte-identical (trace_sha256/message_trace_sha256) against every one of the 65
# public reference traces before being kept. The logEvent fast path (see config.py) skips
# the deepcopy + self.log append for the ~51% of logged events (HOLDINGS_UPDATED,
# QuerySpreadMsg, BID_DEPTH/ASK_DEPTH, IMBALANCE, LAST_TRADE, ...) that trace.py's
# extract_trace always discards -- those rows never reach trace.parquet either way.
#
# Deliberate exception to the org's Python 3.13 standard: ABIDES requires pandas 1.x, which
# publishes no cp313 wheels. This image is self-contained (the harness only reads the parquet
# it writes), so this does not constrain the 3.13 evaluation container.
# ---------------------------------------------------------------------------------------------
# Stage 1: fetch + patch ABIDES, then Cython-compile ABIDES and the adapter (needs a C compiler,
# which stays out of the runtime image).
# ---------------------------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim AS build

ARG ABIDES_REPO=https://github.com/jpmorganchase/abides-jpmc-public.git
ARG ABIDES_COMMIT=f9cbe51342b7dedd9587e4e069040d68a5c6477f

ENV PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*
RUN pip install cython==3.3.0 setuptools

# Apply, in order:
#   1. order_size_model.pomegranate-free.patch — drop the unbuildable pomegranate dependency.
#   2. kernel_message_ledger.patch — observation-only per-message ledger for the trace schema.
#   3. exchange_protocol_stp.patch — opt-in self-trade-prevention policy.
#   4. oracle_scheduled_jump.patch — opt-in deterministic fundamental jump.
#   5. debug_log_guard.patch — guard ~86 `logger.debug`/`logger.info` call sites (kernel.py,
#      order_book.py, trading_agent.py, exchange_agent.py) behind `isEnabledFor` so their
#      (often eager f-string/.format()) arguments stop being built and discarded on every
#      event at stdout_log_level="WARNING". Mechanically generated (AST-based), zero logic
#      change. Measured: byte-identical trace/message_trace hashes before and after.
#   6. kernel_heapq_tuple_ledger.patch — the kernel's queue.PriorityQueue (a heapq behind a
#      lock + two condition variables) becomes a bare heapq list: same heap, same tuple
#      comparisons, same pop order, no locking in a single-threaded loop. Message-ledger rows
#      become tuples instead of 9-key dicts (trace.py builds the columns from them directly).
COPY patches/ /tmp/patches/
RUN git clone "${ABIDES_REPO}" /tmp/abides \
    && git -C /tmp/abides checkout "${ABIDES_COMMIT}" \
    && git -C /tmp/abides apply /tmp/patches/order_size_model.pomegranate-free.patch \
    && git -C /tmp/abides apply /tmp/patches/kernel_message_ledger.patch \
    && git -C /tmp/abides apply /tmp/patches/exchange_protocol_stp.patch \
    && git -C /tmp/abides apply /tmp/patches/oracle_scheduled_jump.patch \
    && git -C /tmp/abides apply /tmp/patches/debug_log_guard.patch \
    && git -C /tmp/abides apply /tmp/patches/kernel_heapq_tuple_ledger.patch \
    && mkdir /src \
    && cp -r /tmp/abides/abides-core/abides_core /tmp/abides/abides-markets/abides_markets /src/

# Compile every ABIDES + adapter module (except package __init__s and the CLI entry modules)
# to a C extension. Directives keep Python semantics (no annotation typing, no type
# inference); see build/cy_build.py. Measured ~15% off the simulation loop, byte-identical.
COPY abides_fork /src/abides_fork
COPY build/cy_build.py /tmp/cy_build.py
RUN python /tmp/cy_build.py /src \
    && find /src \( -name "*.c" -o -name "__pycache__" \) -prune -exec rm -rf {} + \
    && rm -rf /src/build

# ---------------------------------------------------------------------------------------------
# Stage 2: runtime.
# ---------------------------------------------------------------------------------------------
FROM --platform=linux/amd64 python:3.11-slim

LABEL qfbench2.interface_version="2.0"

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

# Compiled ABIDES (abides_core, abides_markets) + the `simulate`/`simulate-batch` adapter.
COPY --from=build /src/ /opt/
COPY simulate /usr/local/bin/simulate
COPY simulate-batch /usr/local/bin/simulate-batch
RUN chmod +x /usr/local/bin/simulate /usr/local/bin/simulate-batch

WORKDIR /work
CMD ["simulate", "--help"]
