# Book-history analysis experiment

## Executive summary

The completed candidate removes the temporary L2 DataFrame while preserving dtype
inference over the full timestamp column. Exact event and message traces, all
50 developer checks, independent source/gate audits and regression65 (65/65) pass.
The preregistered full-run criterion fails: primary deep-book median is 1.15%
slower, and the s001 guardrail median is 14.93% slower. Verdict:
`not_supported_regression_guardrail`. The 2.248x runtime synthetic accounting
component ratio does not establish a faster simulation. Stage 2 remains a separate
rejected prototype because historical mutable aliases invalidate cached metrics.
All findings are local preliminary evidence with `rankable=false`.

## Stage 1: remove the remaining DataFrame

The common commit is `0af6939d8815b9e39376e5c6f7fef3538cec06f1`; its reducer
already scans Python records exactly. The frozen source snapshot already has that
patch. This overlay replaces only the residual `pd.DataFrame(book)` and endpoint
subtraction in `ExchangeAgent.get_time_dropout`, with a Series containing only the complete QuoteTime column.
Whole-column pandas dtype inference preserves the existing integer/object scalar
and zero-duration division behavior (including NaN or ZeroDivisionError), while
timestamps above 2^53 remain exact. This still costs O(n) CPU and temporary memory;
it removes the DataFrame and L2 columns, rather than reducing timestamp work to O(1). No reducer,
matching, imports, adapter, logging, scorer, cards, thresholds or references change.

`apply_overlay.py` requires the exact frozen exchange source SHA-256
`07b2c71633b40e3ada1582a8d5187998d1e92fde63995e7669a0261979bcaab3`,
and refuses unknown sources and a second application. The runtime check reverses
only this transformation and verifies that same baseline hash. The Docker
layer changes the installed exchange module only. The untouched pandas import is
still needed by other exchange methods and is outside this hypothesis's scope.

Tests extract the real pinned method from the frozen source, apply the exact
shipping transformation, and compare every metric and scalar type. Cases cover
empty histories, zero duration, open trailing gaps, repeated/nonmonotonic times,
nanosecond values above 2^53 and arbitrary integers above int64, including a
middle 2**100 outlier with small or identical endpoints. Real upstream
`get_L1_snapshots`, `get_L2_snapshots`, and `logL2style` consumers remain valid;
`logL2style` still exposes the original ndarray identities. No pytest is installed
in the overlay: `runtime_check.py` uses the container's existing dependencies.

## Stage 2: incremental accounting and compact-history assessment

`prototype.py` observes rows incrementally, preserving all original L2 history
rows. Its prefix totals exactly match the integrated reducer, including open
trailing gaps. The microbenchmark includes every incremental update, as well as
history appends and finalization. Nine host repeats at 100,000 depth-10 snapshots
show a 1.1244 ratio versus append-then-scan (26.948 ms versus 23.966 ms) in the
latest repeat. Host repeats varied materially (earlier ratios 1.0207 and 0.9606);
these narrow accounting measurements leave the compatibility objection unchanged.
This narrow synthetic number is not a full-run speedup claim.

The API compatibility test demonstrates why this prototype is not shipped:
`book_log2` contains mutable dicts and ndarrays, and `ExchangeAgent.logL2style`
returns their actual references. Editing a previously observed row invalidates
incremental metrics. Retaining exact arbitrary mutation behavior requires replay
or a broader API design. `OrderBook.get_L1_snapshots` and `get_L2_snapshots` consume
all rows, so deleting snapshots or replacing them with compact boolean summaries
would break public consumers. A lazy compact representation would also change
identity/mutation semantics unless materialization ownership is redesigned.
No compact-history runtime change is included. This is a rejected compatibility
prototype, rather than a candidate hidden inside stage 1.

## Reproduce local checks

Run from this worktree; the source path is the manager's immutable host snapshot.

```bash
T3_PY='/Users/iopogiba/Documents/HSE/Year 1/Module 3/infra/track3-simulation-public/.venv/bin/python'
BOOK_HISTORY_BASE_SOURCE='/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/baseline-source' \
  PYTHONPATH="$PWD:$PWD/baselines:$PWD/experiments/book-history" "$T3_PY" -m pytest -q \
  experiments/book-history/test_history.py tests/test_dropout_python_control.py
PYTHONPATH="$PWD:$PWD/baselines:$PWD/experiments/book-history" "$T3_PY" \
  experiments/book-history/microbenchmark.py \
  --base-source '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/baseline-source' \
  --out experiments/book-history/evidence/microbenchmark-host.json
```

The host microbenchmark excludes matching, startup, trace I/O and retained history
construction. Stage 1 analysis medians are 53.383 ms versus 34.843 ms. Its measured
tracemalloc temporary peaks are 7,404,013 versus 6,602,657 bytes. The full
timestamp Series retains O(n) allocations to preserve dtype inference. Tracemalloc runs are
separate from timing repeats. One warmup precedes each group; the full simulation
campaign uses paired AB/BA/AB ordering independently.

## Parent-owned Docker slot and full-run commands

Only the parent builds/runs Docker. `build-plan.json` carries absolute context and
Dockerfile paths, the image tag, container verification argv and five workloads.
The base image's immutable digest must be supplied/recorded by the parent.

```bash
docker --context colima-agenthon build --platform linux/amd64 \
  --build-arg BASE_IMAGE=hotpaths-base:20261006 \
  -f experiments/book-history/Dockerfile -t hotpaths-book-history:20261006 .
docker --context colima-agenthon run --rm --network none --platform linux/amd64 \
  hotpaths-book-history:20261006 python /opt/book_history_experiment/runtime_check.py
PYTHONPATH="$PWD" "$T3_PY" scripts/run_differential_experiment.py run \
  --baseline-image hotpaths-base:20261006 --candidate-image hotpaths-book-history:20261006 \
  --baseline-commit 0af6939d8815b9e39376e5c6f7fef3538cec06f1 \
  --candidate-commit "$(git rev-parse HEAD)" \
  --units-dir '/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/public-units' \
  --units t3-s001-price-time-priority t3-as05-oracle-variant \
          t3-st01-liquidity-churn-baseline t3-mr-deep-book-state-size t3-gbatch-homog-4 \
  --repeats 3 --out out/book-history/full-run
```

The batch adapter's known root-profile contract issue must be handled by the
parent's explicitly declared contract-only wrapper, identically for both roles;
record its image/source identity and original refusal separately. It is not a
history optimization. Primary workload is `t3-mr-deep-book-state-size` because it
stresses retained depth/state. Churn is secondary; oracle and s001 check other
paths; homog-4 checks batch isolation. The harness must pass exact event and
message ordered equality plus unchanged full developer gates, including C3 and
digest audit, with a warmup pair, three unprofiled AB/BA/AB pairs and a separate
profile pair. Preliminary adoption requires at least 5% reduction in primary
full-run median. Warmup/profile values never enter that median.

`result.json` contains completed full-run values from the manager
and independently verified evidence. The local `AGENTS.md` was followed; its referenced
`../../AGENTS.md` does not exist in this worktree hierarchy.

## Runtime component plan

The current shipping implementation is `8df2c59b031b9fee6c7b468ee326a2c3acb37017`, recorded
in `build-plan.json` and `result.json`; an evidence-only commit records that identity after implementation.
The earlier `cfbb82113c8ec803d28651c759dece235a74d9c7` endpoint candidate is superseded.
`build-plan.json.component_commands` runs the same microbenchmark with the image
Python 3.11, `/checks` bound to the experiment, `/baseline` to the immutable common
source and `/repo` to this worktree (all read-only), `PYTHONPATH=/repo:/opt`, and
a separate writable `/evidence` mount. Its output is
`/evidence/microbenchmark-runtime.json`; host and runtime measurements stay distinct.
The runtime also verifies the installed exchange source is precisely the pinned
baseline plus this overlay. No Docker invocation has been made by this agent.

## Independent review correction

The initial endpoint-only NumPy candidate incorrectly inferred dtype when an
interior timestamp was 2**100 and endpoints were small. On endpoints 0/0, the
original object column raised ZeroDivisionError whereas that candidate produced
NaN. On endpoints 0/1, metrics changed from Python float to numpy.float64. The
manager identified this case; `evidence/middle-outlier-before-fix.txt` preserves
two actual failing comparisons. The meaningful regression cases now pass against
the real source. `evidence/microbenchmark-host-superseded-endpoints.json` retains
the original faster but invalid candidate's measurements and must not support the
current candidate's claims. The corrected overlay uses only the whole timestamp
Series and leaves Stage 2 unchanged. Image runtime checks cover both middle-outlier
cases; All Docker runs were executed by the parent; this agent did not run Docker.

## Completed parent-owned campaign

One warmup pair, three unprofiled AB/BA/AB pairs and a separate profile pair
completed on each of five units. The manager recomputed container lifetimes from
Docker State; warmup/profile values are excluded from all medians below.

| Unit | Baseline median s | Candidate median s | Time reduction | Ranges overlap |
|---|---:|---:|---:|---|
| t3-s001-price-time-priority | 1.582286563 | 1.818454074 | -14.93% | no |
| t3-as05-oracle-variant | 3.013023346 | 3.028956772 | -0.53% | yes |
| t3-st01-liquidity-churn-baseline | 4.691757230 | 4.754189996 | -1.33% | yes |
| t3-mr-deep-book-state-size | 19.966732604 | 20.195463629 | -1.15% | no |
| t3-gbatch-homog-4 | 3.548767140 | 3.091822712 | +12.88% | yes |

Primary deep-book and s001 have non-overlapping observed ranges in the slower
direction. Batch shows a +12.88% median time reduction with overlapping ranges;
it does not rescue the failed primary >=5% reduction and <=5% regression guardrail.
No causal explanation for the slowdown is established. The inherited exchange
bytecode caches are invalid in both images; as-built cold start/recompilation is
included in full-run container lifetimes. These are not steady-state timings.

The runtime Python 3.11 synthetic accounting benchmark measures 119.449 ms versus
53.130 ms (2.248x), with temporary peaks 7,403,791 versus 6,602,745 bytes.
Its full samples are retained separately. The stage-2 prototype measures a 0.9924
accounting ratio including updates, retains original rows, and is not shipped.
The measured stage-1 scope is the full QuoteTime Series; removing snapshots or
using the endpoint-only candidate is not part of these final runs.

Independent source reconstruction from the implementation commit matches all 52
installed Python files; only exchange_agent.py differs from the common base.
80 independent pair trace checks pass byte, schema and ordered-value equality.
All 50 launches pass C3, g0–g3 and digest declarations. A separate deep-book gate
recheck also passes. The complete regression65 was executed on the original
candidate image, with 65 passed, 0 failed and 0 errored; it was not reused evidence.
The identical contract-only batch CLI wrapper deletes only forbidden root
profile.json after successful serial batch execution; its original C3 refusal
is retained separately. Scorer, cards, references and thresholds are unchanged.

Immutable image identities:

- common_base: `sha256:7097baadcc6b889cdc539aa8e2afbafbb5a1da7724428c93b6d334b4528a3767`
- candidate_without_contract_wrapper: `sha256:766b3f49b285ec909f423e8078bc0c2e45c30ddc1de2e5905bad4c08fb5b65e0`
- baseline_timed_contract_control: `sha256:443d01e90bf00ff92f77d71bf672fc2a032b7df401647ac694267e8107da5d40`
- candidate_timed_contract_control: `sha256:4c35b44a353573e875a286f12f51fb1011792b3e772229a4e2c8902addc1c685`
- regression65_candidate: `sha256:766b3f49b285ec909f423e8078bc0c2e45c30ddc1de2e5905bad4c08fb5b65e0`

Common source commit: `0af6939d8815b9e39376e5c6f7fef3538cec06f1`. Implementation:
`8df2c59b031b9fee6c7b468ee326a2c3acb37017`. Exchange baseline/candidate SHA-256:
`07b2c71633b40e3ada1582a8d5187998d1e92fde63995e7669a0261979bcaab3` /
`29a2a2304816d284fb8e6edf40db6b607cf8979f08ec80d1e6ef162ad56e9d16`.

`result.json` contains every raw timing pair, AB/BA order, observed range and
absolute record path with SHA-256. The final evidence index binds the following
parent artifacts by absolute path and SHA-256:

- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/pipeline.json` — `8fc5d33b6d59e0f973b7918e1fc354e75130c97e047215085a59f5c5d9ee1881`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/manager-audit.json` — `be26d81fcd2ae9910254e9f158a47df19fd6541e5f7d849701c17aff0e3d5604`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/manager-audit.events.jsonl` — `21e41fa5a69085e0703468683f252b65f88ae38185d441c2fcb3210f6b96e041`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/independent-source-audit.json` — `e321d265c78e9b6b5ca1ca480e3b21446317b5269f487ebcb2d6af41f80e0326`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/source-audit.json` — `9e5312be7d169f05054f42ab82818cb13e28cf9ead87f62bf46529f526bf88d0`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/bytecode-cache-inventory.json` — `27c2db24f2a9c97455a361e75a6a6ca2a6eae152a23cea12952458b277f2d758`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/components/microbenchmark-runtime.json` — `e59833700d198f0a28c80c635b6e3cbe2cf04f9042659aaa3b4690f234c9b672`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/differential/summary.json` — `9d1ac4d61dacf84fdd8f245ff7b6cd6f8ffdd93b2ba27dd0c7723ec98c0f3357`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/manager-gate-recheck/summary.json` — `7e8dc9bea834da3dc8cf9aa33b81911cc43ca97b35a3cb46ad00fdc2537bbe1b`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/regression65/report.json` — `5cf1525ecdd21e0e4125630811e3ac9abca732faefb37fa48843615663025aa3`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/regression65.command.json` — `1cc3357ee2fc8e5835b3053017e2a9b9121453552643ad3143f2f2c9b5c43a1e`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/differential.command.json` — `f83b5b40b78d8644305387afd01af5d056f62dff2486fc7eb87afd9f039274cd`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/build.command.json` — `c4942c61991907d999842b49fda18febc26b375b5826f875a2566c4fefc6c498`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/build-control.command.json` — `d94619a8079496e83360f9be13a6f912413ad3751f3833a62a75c325d6dcf54a`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/runtime-00.command.json` — `08c304e99f2d8509785fcf1478542fc6c679d23a2c7aeacb0013d46d0aed3558`
- `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/book-history/component-00.command.json` — `2a55132e5313171317fa17adae28920d38383d0e26bff757f6b92ca43b7c374b`

The manager audit additionally binds all retained raw records and trace files.
Profile diagnostics are preserved in the differential run directory and are
excluded from performance medians. Completion requires the parent pipeline flag
and the actual successful 65-scenario report, both verified before this final write.
