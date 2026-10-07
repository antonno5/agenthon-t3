Executive summary. Disabled DEBUG formatting guards preserve the checked market
events and reduce full-run median time by 6.84% on momentum and 8.64% on
deep book. Both fixed targets clear the 5% criterion; no selected median
slowdown exceeds 5%. All 65 public regression scenarios pass. The verdict is
`local_gain_supported_requires_linux_confirmation`: preliminary local evidence
with `rankable=false`, requiring independent Linux confirmation before adoption.

# Experiment 1: disabled DEBUG argument preparation

Shared base: `0af6939d8815b9e39376e5c6f7fef3538cec06f1`. Implementation: `a686ac924382c03571e6a9c7cd9612abab1679ef`.
Runtime harness-only repair: `4fd35694daf770135e03dcb1904ec1ceeaf91255`.
Machine-readable measurements, all pairs, source hashes and absolute evidence
paths with SHA-256 are preserved in [result.json](result.json).

## Change and correctness

The patch adds 65 `logger.isEnabledFor(logging.DEBUG)` guards in six upstream
files: Agent, Kernel, ExchangeAgent, TradingAgent, SparseMeanRevertingOracle
and OrderBook. DEBUG-enabled statements and message text remain unchanged.
Existing lazy arguments and existing guards remain untouched. No cached level
is introduced. The common source already contains dropout_python_control and
STP. No other hypothesis, scorer, unit/reference or tolerance change is imported.

22 host tests cover actual callback state/events, enabled DEBUG output, disabled
rendering, unchanged wakeup scheduling and shallow container mounts. Twelve
Docker callback cases pass on Python 3.11.17 and bind installed TradingAgent
SHA to the prepared candidate. Independent reconstruction from the committed
patch matches all 52 installed Python files. Every selected run passes actual
g0–g3 gates; both traces match bytes, schemas and ordered values. The manager
independently checks 25 pairs, 50 trace comparisons, Docker event coverage and
absence of overlapping execution, then freshly rechecks the momentum gates.
All 65 standard public regression scenarios pass (0 failed, 0 errored). This
is not an all71 exact-trace simulator admission.

## Full-run measurements

One warmup pair, three fresh-container unprofiled pairs in AB/BA/AB order and
one separate profile pair per unit, strictly sequential in the parent Docker
slot. Each container gets 4 CPU, 16 GiB, equal swap and no network. Disk quota
is not enforced. Full-run clock is Docker State FinishedAt minus StartedAt;
the manager recomputes the medians. Warmup/profile clocks are excluded.

| Unit (prefix t3-) | Baseline median s | Candidate median s | Reduction | Paired speedup median | Ranges overlap |
|---|---:|---:|---:|---:|---|
| s001-price-time-priority | 1.556418 | 1.601346 | -2.89% | 0.9555× | True |
| momentum-mix-priority | 5.150710 | 4.798423 | 6.84% | 1.0771× | False |
| mr-deep-book-state-size | 18.648023 | 17.037034 | 8.64% | 1.1161× | True |
| mp01-stp-newest-baseline | 4.866266 | 4.477171 | 8.00% | 1.0869× | True |
| mp02-stp-oldest-baseline | 4.647711 | 4.053574 | 12.78% | 1.0982× | False |

Acceptance targets were fixed before simulator timing: momentum and deep book.
Each needs >=5% median full-run reduction; any selected median slowdown >5%
fails the guardrail. Both targets pass, and s001’s 2.89% slowdown is below
the guardrail. Speedups use ratios of medians; paired ratios are also retained.

| Unit | Three baseline/candidate pairs s | Baseline range s | Candidate range s |
|---|---|---|---|
| s001-price-time-priority | 1.634822/1.710960; 1.556418/1.601346; 1.477739/1.580271 | 1.477739–1.634822 | 1.580271–1.710960 |
| momentum-mix-priority | 5.433013/4.812975; 5.150710/4.798423; 5.040510/4.679816 | 5.040510–5.433013 | 4.679816–4.812975 |
| mr-deep-book-state-size | 17.782150/15.932969; 21.578190/17.037034; 18.648023/17.790071 | 17.782150–21.578190 | 15.932969–17.790071 |
| mp01-stp-newest-baseline | 7.251973/2.312439; 4.866266/4.477171; 4.499236/4.644250 | 4.499236–7.251973 | 2.312439–4.644250 |
| mp02-stp-oldest-baseline | 4.868073/3.912483; 4.451541/4.053574; 4.647711/4.236679 | 4.451541–4.868073 | 3.912483–4.236679 |

Only three pairs provide limited precision. Momentum has non-overlapping ranges
and all three pairs faster. Deep-book ranges overlap slightly despite all three
pairs being faster. s001 and mp01 ranges overlap; mp01 is particularly noisy
and its third pair is slower. No significance or general simulator claim is made.

The original complete mp02 schedule was rejected because Docker State timestamps
overlapped by 52.197569 ms despite serial foreground launches and earlier destroy
events. The manager replaced the entire unit schedule (warmup, three pairs and
profiles) on identical immutable images. Selection was based only on clock
validity. No cherry-picked repeats or extra speed-based repeats are used.
Original evidence and clock-retry-policy.json remain retained.

## Isolated component and diagnostic profiles

Docker Python 3.11 component medians: 1.091839/0.025065 s for
200000 actual order_accepted calls with actual LimitOrder.__str__, fmt_ts and
dollarize bodies. Each process warms 1000 calls; three pairs use AB/BA/AB.
Order rendering falls from 200000 calls to zero. This isolated result does not
replace the full-run criterion. Preliminary host component samples remain separate.

Ten later detailed profiles are diagnostic only; their complete phase/component
times and call counts are stored in result.json. Instrumented times are excluded
from speed estimates. Adapter/RSS/residual medians are retained separately;
RSS is self-reported process high-water, while host cgroup/RSS sampling is unavailable.

## Runtime, provenance and retained evidence

Host: Mac ARM64, Colima linux/amd64 via Rosetta. Runtime Python 3.11.17, numpy
1.26.4, pandas 1.5.3, pyarrow 15.0.2 and scipy 1.17.1 are identical. Checker
Python 3.13.3 uses shared qfbench2-common 2.4.4. These are developer measurements
and cannot establish official Linux/B200 performance.

Base image: `sha256:7097baadcc6b889cdc539aa8e2afbafbb5a1da7724428c93b6d334b4528a3767`.
Candidate image: `sha256:ca54db4e1d7e32f6fcf00a277fddcbb310ad8132a5539d4cb4006e7c94f0a681`.
Measured baseline: `sha256:443d01e90bf00ff92f77d71bf672fc2a032b7df401647ac694267e8107da5d40`.
Measured candidate: `sha256:85108ab5ca9df52e9ac5693c47b43335034aa8b77f1c453cdd8b49d12c3c5b19`.

Both measured images have the same contract-only simulate-batch wrapper removing
forbidden root profile.json after successful serial batches. It does not affect
any of these five single-scenario measurements. No simulation logic changes in
that wrapper. Patch/control/input/reference hashes and exact commands are retained.

Parent evidence directory: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/debug-logging`.
Initial failed runtime mount evidence: `/Users/iopogiba/Documents/ChatGPT/Агентон/orchestration/2026-10-06-hotpaths/runs/debug-logging-failed-runtime-mount/runtime-00.log`.
The initial mount failure occurred before callback execution; the harness repair
selects DEBUG_PREPARED before resolving repository parents. Source/patch stayed
unchanged. Successful runtime and failed-clock evidence remain separate.

result.json stores SHA-256 for pipeline, audits, summaries, gates, regression,
commands, component records and independently checked trace files. Dockerfile
and exact mounts/runtime commands remain in build-plan.json. No new Docker run
or benchmark was started during final reporting. No merge, push or integration.
