Executive summary. Direct price and order lookups preserve the tested trading
results, but this experiment should not be adopted under its agreed criterion.
The full cancellation-churn run improved by 4.16% and the deep-book run by 2.46%;
both needed at least 5%. All 65 public regression scenarios passed. The indexes
consume extra memory, and one selected lifecycle load slowed down by 12.91%.
These are local developer results (`rankable=false`), not official Final timing.

# Experiment 2: book indexes

Base: `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`.
Branch: `codex/exp-20261005-02-book-index`.
Tested implementation/tooling revision: `65846ad23909603a1414a3bd0fbf1762063b2b07`;
the following report-only commit records this conclusion.
Upstream: [pinned ABIDES](https://github.com/jpmorganchase/abides-jpmc-public/tree/f9cbe51342b7dedd9587e4e069040d68a5c6477f).
Machine-readable evidence: [result.json](result.json).

## Change and semantic boundaries

`baselines/patches/book_index.patch` applies after the four official patches.
The standard Dockerfile applies it at build time. The experiment's overlay
Dockerfile changes only `order_book.py`, `price_level.py` and the new
`indexed_order_queue.py` inside the immutable baseline image. Its baseline-source
hash check rejects an image with a different OrderBook, including an image without STP.
No adapters, reference files, unit cards, scorer or tolerances change.

Each side has a price-to-level dictionary plus ascending search keys (negative bid
prices). Existing prices use the dictionary; new prices and last-order level
removal use bisect. Level lists remain available for best-level matching and depth
queries. Insertion/removal still shifts list entries: this experiment removes the
linear search, not the cost of shifting a price list.

Inside each PriceLevel, visible and hidden FIFOs use an OrderedDict of entries
with an order-id-to-entry-token index. Cancellation and quantity changes address
the entry directly. FIFO head removal no longer shifts all the remaining orders.
No quantity aggregate is cached; existing logging and depth methods still sum the
same visible orders.

The visible-before-hidden rule and partial-fill priority are retained. Increasing
quantity moves the first matching ID to the tail; decreasing quantity keeps its
position. `insert_by_id` still uses the pinned ordering rule and takes linear time.
Duplicate IDs keep first-match semantics through token buckets; duplicate-ID
bucket updates can be linear in the number of duplicates. Index lookups include
the request's side and price so a stale or wrong-price cancellation remains a
no-op. Price-to-comply links, recursive half cancellation, both STP policies,
quiet behavior, history and outgoing message payloads are left in the pinned
methods. Their existing unusual modify/partial-cancel behavior is preserved.

The consumer audit of the pinned archive found queue access in PriceLevel,
OrderBook depth queries and upstream tests. Production consumers use iteration,
length and FIFO head access; those remain supported. Arbitrary list mutation by
new external code is not a supported contract of this experimental queue.

## Correctness and provenance

- 47 differential cases passed on checker Python 3.13 and again in Docker Python
  3.11.17. Three seeded streams of 700 operations compare levels, metadata,
  messages, history, transactions, logs and L2/L3 after every operation. Cases
  cover FIFO, hidden orders, duplicates, price-to-comply halves, STP policies,
  lifecycle changes and last-order level removal. Index invariants and four
  no-iteration tests verify that direct lookup replaces the searches.
- 43 pinned upstream book tests passed for each image in Python 3.11.17; the same
  43+43 source-level tests also passed on the checker. Upstream tests import the
  installed ABIDES modules. Pure Python pytest tooling was mounted read-only;
  simulation dependencies and images were not modified to run tests.
- All seven requested units existed, with no substitutions. The initial 14 gate
  runs and every one of the 60 paired/warmup/diagnostic runs passed the full
  developer verifier (g0–g3) and exact rows plus SHA-256 bytes for both
  `trace.parquet` and `message_trace.parquet` against unchanged public references.
- Public regression: **65 passed, 0 failed, 0 errors**, complete checkpoint. This
  invokes unchanged standard semantic/stylized checks and is separate from the
  seven-unit full verifier and two exact-trace checks.
- All 71 public unit manifests and firewall checks passed using the shared
  library. Ruff and `git diff --check` passed. Five synthetic reporting/identity
  tests and a bounded-worker checkpoint smoke passed; they are tooling checks,
  not simulation or speed evidence.

The differential loader executes real pinned book/order/message code, with
stand-ins only for owning-agent/core utilities. Four downloaded source files are
hash-locked. `out/book-index/application.json` records applied source/patch hashes.
An early preparation defect skipped STP in a nested worktree; the corrected
preparation uses `GIT_CEILING_DIRECTORIES`, asserts STP is present, and checks
expected STP counts. Only corrected runs count. A build attempt using the raw
image ID as `FROM` was rejected by BuildKit; the successful build used the local
baseline tag, verified against the immutable ID before and after. Initial test
mount/tooling attempts are retained separately; final runtime tests all passed.

Baseline image ID:
`sha256:0bd010981f4f4a8aa8bdd074e5342a56bfe91daf25e5c5d7e04c075d082c99e2`.
Candidate image ID:
`sha256:e9f782eade2707fcd537dadbb9e7bd9c9d3c9d0953015db165f035375d827a67`.
Candidate patch SHA-256:
`a3db0378f3d6a4ace641254fc587049e70d3d892bebbc6e1eca05d3ab35a60d1`.
All launches used immutable IDs. Probes confirmed linux/amd64, equal Python
3.11.17, numpy 1.26.4, pandas 1.5.3, pyarrow 15.0.2, scipy 1.17.1,
coloredlogs 15.0.1, prepared market-source hashes, and identical Kernel/adapter
hashes. No runtime code changed after measurement.

## Full-run measurements

One warmup per image/load followed by three unprofiled pairs in AB/BA/AB order,
strictly sequentially in the manager's exclusive slot. Each run used a fresh
container/interpreter, buffered traces, 4 CPUs and 16 GiB. Warmups and the four
later diagnostic profiles are excluded. Positive reduction means faster.

| Load (all names start `t3-`) | Baseline median s | Candidate median s | Full reduction | Simulation reduction | Median paired speedup |
|---|---:|---:|---:|---:|---:|
| `s001-price-time-priority` | 1.767 | 1.596 | 9.69% | 4.82% | 1.1033× |
| `s012-partial-fill-cancel-race` | 16.518 | 13.514 | 18.19% | 14.51% | 1.1885× |
| `cancelmodify-lifecycle` | 10.586 | 11.953 | -12.91% | -10.88% | 0.8857× |
| `mp01-stp-newest-baseline` | 6.930 | 6.111 | 11.83% | 13.62% | 0.9615× |
| `mp02-stp-oldest-baseline` | 5.174 | 5.225 | -0.98% | -4.49% | 0.9864× |
| `mr-cancel-replace-churn` | 21.243 | 20.359 | 4.16% | 6.04% | 1.0072× |
| `mr-deep-book-state-size` | 24.048 | 23.457 | 2.46% | 1.98% | 1.0423× |

The acceptance criterion is the full-run reduction on each of churn and deep
book. Churn's 6.04% simulation-phase reduction does not satisfy its 4.16% full-run
result. The faster s001/s012/STP-newest medians do not substitute for either target.
Median paired ratios and ratios of medians differ, especially on STP-newest;
both are reported rather than selecting the more favorable statistic.

| Load | Adapter median B/C s | Launch/other median B/C s | Warmup B/C s | Process RSS median B/C MiB |
|---|---:|---:|---:|---:|
| `s001-price-time-priority` | 0.218 / 0.180 | 1.559 / 1.416 | 1.716 / 1.738 | 167.33 / 167.50 |
| `s012-partial-fill-cancel-race` | 13.892 / 11.970 | 1.764 / 1.544 | 11.488 / 11.860 | 428.66 / 431.23 |
| `cancelmodify-lifecycle` | 9.045 / 10.337 | 1.542 / 1.582 | 10.167 / 11.050 | 378.58 / 380.89 |
| `mp01-stp-newest-baseline` | 5.081 / 4.447 | 1.703 / 1.664 | 6.024 / 7.451 | 253.80 / 259.18 |
| `mp02-stp-oldest-baseline` | 3.707 / 3.868 | 1.478 / 1.404 | 5.134 / 6.161 | 253.06 / 253.43 |
| `mr-cancel-replace-churn` | 19.362 / 18.456 | 1.881 / 1.903 | 18.162 / 22.682 | 559.94 / 560.88 |
| `mr-deep-book-state-size` | 22.126 / 21.670 | 1.579 / 1.692 | 20.754 / 21.514 | 557.55 / 558.57 |

Phase medians are computed independently and need not sum to the full median.
The warmup warms the host/image cache, not a persistent simulator. No JIT was
added. Three pairs provide limited precision: target sample ranges overlap.
Churn had one slower pair; all three deep-book pairs were faster, but its
ratio-of-medians improvement remains below 5%. Raw samples, ranges and paired
reductions are in `result.json`; no significance claim is made. The execution
host was an ARM64 Mac running linux/amd64 via Rosetta, so these values cannot be
extrapolated to official Linux timing.

## Memory and diagnostic profile

Process RSS above comes from the immutable adapter's Linux
`resource.getrusage(RUSAGE_SELF).ru_maxrss * 1024`, a self-reported process
high-water mark. Container/cgroup peak memory was inaccessible to the host
sampler and remains **null for every load**. Process RSS is not cgroup memory
or signed official evidence. Max as well as median process RSS is saved in JSON.
The regression's maximum recorded process RSS was 1,692,024,832 B (1.58 GiB).

At 10,000 orders over 1,000 bid levels, separate macOS checker Python 3.13
processes measured retained Python book allocations of 3,976,672 B baseline and
6,297,632 B candidate: **+2,320,960 B (2.21 MiB; 58.4%)**. This is the book component,
not a 58.4% increase in full simulator RSS. Peak construction allocations were
3,976,832/6,297,672 B. Shallow index/queue footprint was 248,912/2,938,840 B and may
count shared small integer keys repeatedly. Checker process peak RSS was
106,102,784/118,587,392 B; it includes imports and allocator effects and is not
the Docker runtime assessment.

Four isolated cProfile/component-timer runs followed all timing runs. Each
passed C3 retention, the full verifier and both exact trace comparisons.
Profiles live outside solver output in
`out/book-index/actual-paired/diagnostic/<unit>/<variant>/profiles/`.
Diagnostic matching component time grew from 8.17 to 9.92 s on churn and 9.80 to
12.02 s on deep book. Profiles include instrument overhead and extra queue
method calls; they are useful for locating costs, not estimating speed. The
indexes remove scans but add Python bookkeeping, while queue/kernel/agent and
termination work still consume much of the simulation. This explains why the
algorithmic lookup change alone does not establish a full-run win.

## Public regression execution and recovery

The external manager public-reference map was verified against unchanged unit
configurations and both mapped/local trace hashes for all 65 scenarios. After
all timing and diagnostic runs finished, the manager authorized three bounded
correctness workers. These concurrent regression EPS values are **not performance
evidence**. Each container retained the standard 4-CPU/16-GiB hard caps; 3 GiB per
task was only the scheduling estimate. No scenario errored, so no fallback to one
worker was needed.

`regression.py` calls unchanged `run_scenario` and `build_report`, with live
transport wrappers isolated in worker processes. The parent alone atomically
fsyncs/replaces the checkpoint after each completion. Bounded logs, profiles,
launch/cid metadata, hashes and explicit completeness survive interruption.
Resume verifies the frozen image/runner/semantics/checker/config/reference
contract, serially revalidates saved regular no-follow outputs through unchanged
checks before any live launch, preserves completed failures and launches only
unfinished scenarios. Hash drift is rejected. A fixture smoke verified the
three-worker bound and parent-only checkpoint writes; it is not runtime evidence.

## Reproduction and artifacts

Commands require a new manager-granted slot; the slot for this experiment has
been released. VM lifecycle belongs to the manager. Every Docker operation,
including cleanup/lifecycle calls, uses explicit `--context colima-agenthon`.
Run from this worktree with the external checker environment:

```sh
BOOK_CHECKER='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
export PYTHONPATH="$PWD"
"$BOOK_CHECKER" experiments/book-index/prepare.py
"$BOOK_CHECKER" -m pytest experiments/book-index/test_operations.py -q -o addopts=
"$BOOK_CHECKER" experiments/book-index/upstream_checks.py --out out/book-index/upstream-checks
"$BOOK_CHECKER" experiments/book-index/memory.py --orders 10000 --levels 1000 --out out/book-index/memory.json

docker --context colima-agenthon build --platform=linux/amd64   --build-arg BASE_IMAGE=orchestration-baseline:20261005-a5dbe46   -f experiments/book-index/Dockerfile -t book-index:20261005   out/book-index/candidate/abides-markets/abides_markets
"$BOOK_CHECKER" experiments/book-index/runtime_tests.py
"$BOOK_CHECKER" experiments/book-index/validate.py --mode gates --out out/book-index/actual-gates
"$BOOK_CHECKER" experiments/book-index/validate.py --mode paired --repeats 3 --out out/book-index/actual-paired
DOCKER_CONTEXT=colima-agenthon "$BOOK_CHECKER" experiments/book-index/regression.py   --candidate book-index:20261005 --workers 3   --reference-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-05/public-regression-reference-map'   --out out/book-index/actual-public-regression
```

Use fresh output directories/worktree for reruns: evidence is not overwritten.
`runtime_tests.py` uses its fixed fresh output directory. Regression resume uses
the same command/output with `--resume`; worker count may decrease to one.
Downloads occur during preparation/build, never simulation.

Raw evidence is retained in ignored `out/book-index/`: application and build
logs, runtime tests, `actual-gates`, `actual-paired` (identity, records, summary,
profiles), `actual-public-regression` (complete checkpoint/report, execution,
scenario logs), `measurement-analysis.json`, and independent manager audit.
The committed `result.json` preserves full per-load measurements, identities,
source/patch hashes and evidence paths without copying public reference traces.

## Verdict

**do_not_adopt — performance criterion not met.** Correctness passed within the
reported scope; both required full-run improvements are below 5%, and lifecycle
regressed. No more repeats were selected after seeing results. The known baseline
batch root `profile.json` retention failure remains unchanged: these selected
units and public single-scenario regression do not resolve batch admissibility.
No cards, tolerances, scorer, standard regression functions or references were
changed to accept the candidate. Docker slot released; no push or merge.

## Development decision updated on 6 October 2026

The indexed implementation was removed from the active `codex/develop` build
after the user questioned the lifecycle slowdown. This is a historical report.
Run its reproduction commands in `codex/exp-20261005-02-book-index`, which retains
the patch, tools and complete experiment. The current development engine remains
the original four-patch baseline; the differential checker is integrated.
