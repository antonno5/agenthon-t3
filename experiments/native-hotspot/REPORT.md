Executive summary: This experiment preserves trades and messages but does not earn adoption as a faster simulator. A small compiled function speeds up final order-book bookkeeping. On the main test, however, the whole container took 2.84% longer than baseline and 5.40% longer than the simpler Python alternative. The required 5% improvement was missed. Keep the result as a completed negative experiment. All 65 public regression scenarios passed.

# Experiment 5: native liquidity-gap reducer

Base: `a5dbe466f038389e96f44d6f71f1258e2eddcbb5`. Branch:
`codex/exp-20261005-05-native-hotspot`. Verdict: **do_not_promote_native**.
The three requested units were used without substitution. All evidence is local
and `rankable=false`: Mac ARM64 host, linux/amd64 Docker emulation,
`colima-agenthon`. It does not establish official Linux CPU or Final performance.

## Full-container result

Each workload/image received one warm-up, three unprofiled runs in alternating
forward/reverse variant order, and one separate diagnostic run. All 45 runs were
serial. Only the 27 unprofiled runs contribute to these median seconds.
A positive reduction means faster than baseline.

| Unit | Baseline | Python control | Native C | C reduction vs baseline | C reduction vs Python |
|---|---:|---:|---:|---:|---:|
| s001 price-time priority | 1.896428 | 1.948300 | 1.850981 | +2.40% | +5.00% |
| oracle-variant (primary) | 4.103317 | 4.003593 | 4.219865 | **−2.84%** | **−5.40%** |
| cancel-replace churn | 23.208059 | 19.383103 | 18.100032 | +22.01% | +6.62% |

The primary oracle threshold is at least 5% full-container reduction; it fails.
`strict_each_unit=false` is the supplementary all-workloads threshold. Python
also misses the primary target (+2.43%); this experiment does not promote it.
The churn improvement is useful diagnostic evidence but cannot replace the
predeclared primary criterion. Churn C is faster than Python in only one of
three pairs: baseline [24.970080, 23.208059, 19.094026], Python
[19.733967, 19.383103, 16.706432], C [24.070260, 18.100032, 16.859211] s.
Its positive incremental median is unstable. Direct-row Python is the cheaper
workload-specific candidate for a future churn experiment (+16.48% observed
median reduction), without promotion from this experiment. No extra repetitions
were added to chase a win.

Oracle paired Python-minus-C seconds were −0.166386, −1.538455, +0.397758.
The mixed signs and a 5.542048 s native run show substantial variation.
Median time outside the adapter was baseline 1.747853 s, Python 1.791486 s,
C 1.903695 s. This includes startup/imports and transport; it is not isolated
import timing. Every repetition starts a new Python process. Adapter medians
were 2.376775 / 2.104035 / 2.257841 s; simulation medians were
2.093192 / 1.861340 / 1.970850 s (baseline / Python / C).

## Exactness and actual runtime

The active native image uses Python 3.11.17, NumPy 1.26.4, pandas 1.5.3 and
PyArrow 15.0.2. Actual installed `ExchangeAgent.get_time_dropout` passed 109
boundary/random histories against original and Python control. The loaded helper
is a compiled builtin at `/opt/_abides_native_hotspot.so`, 16,504 bytes,
SHA-256 `5d2bd2542ff76785a78250e1955eca77c4f6d5df52e164df87c9ec51aa27d9ec`.
There is no JIT. Profiles confirm the simulator invokes that builtin once per
symbol book, including oracle and churn.

All 45 serial runs passed developer checks. Both `trace.parquet` and
`message_trace.parquet` matched across all variant pairs in schema, ordered
values and bytes, and matched the frozen reference hashes. A further nine
runs through unchanged bounded `throughput.run_unit` passed all developer gates
with shared C3 no-follow retention and exact retained companion traces.
Those nine runs are excluded from timing medians.

The native-only public regression completed: **65/65 PASS**, `complete=true`,
zero failures and zero errors. All 130 saved trace/events hashes were verified
against the parent checkpoint; all scenarios were executed in this run.
The unchanged standard regression runner consumes the external public reference
map; no references are copied into this repository. Up to three containers,
each limited to 3 GiB memory/swap, are used solely for correctness. Checkpoints
are parent-only and atomic. Regression events/sec is not benchmark evidence.

The prior local 43-check suite, six recovery checks, single multiprocessing
smoke, selected manifests and all 71 public-firewall checks passed. These remain
separate from the actual Linux simulator validation.

## Why the component win did not justify C

The current baseline oracle diagnostic attributes 0.754350 s of 7.146322 s
to `get_time_dropout` (10.56%). Its infinite-section Amdahl ceiling is about
1.118× under instrumentation, not a prediction for unprofiled container time.
Diagnostic method totals are baseline 0.754350 s, Python 0.027682 s and
C 0.026554 s. Most savings come from removing pandas row wrappers. The native
helper itself takes 0.001900 s, versus Python helper 0.008423 s, but both retain
the original DataFrame allocation and metric arithmetic.

On the synthetic 7,541-row component in the actual image, medians are
0.161148 / 0.006013 / 0.004267 s (original / Python / C): C is 37.76× faster than
original and 1.41× faster than direct Python. Component timings exclude imports,
row creation, simulation and build. Additional Python heap peaks are
819840 / 561808 / 561768 bytes, excluding the input book. They are not RSS.
The retained macOS checker diagnostic is historical and does not replace these
runtime measurements.

Oracle median peak process RSS was 209244160 / 209154048 / 209141760 bytes.
Churn was 587857920 / 586350592 / 583598080 bytes; s001 was approximately
175.5–175.6 million bytes. These are self-reported process peaks, not official
cgroup memory. The reduction is modest because the DataFrame remains.

## Build and maintenance cost

The compact compiler stage pins GCC and C headers from the signed Debian
snapshot documented in README. The final image copies only the extension and
patches one method; no compiler or new runtime package enters it.

| Cost | Native C | Python control |
|---|---:|---:|
| First build seconds (baseline already cached) | 19.754737 | 2.075951 |
| Cached build seconds | 0.440551 | 0.365196 |
| Docker reported image bytes | 179151005 | 179147633 |

C adds 17.678786 s to this first-build comparison plus CPython ABI and C/binding
maintenance. With no primary full-run savings over Python, runtime payback is
unavailable. Cached rebuild changed Docker image IDs although its stages were
reported CACHED; the cold ID ceased to resolve. Active-image parity was therefore
rechecked after timing and passed with the same extension hash. RootFS equality
is not asserted. Timing and regression pin the active immutable ID.

## Evidence

Compact runtime evidence is committed under `evidence/runtime-20261006/`.
`result.json` contains numeric primary speedup, build costs, per-unit timing,
verdict, exact commands and completion status. Raw logs, retained outputs and
nine raw cProfiles with command manifests remain at
`out/native-hotspot/runtime-20261006/`; profile hashes are committed.
The experiment changes no official scorer, cards, tolerances, public configs,
references, baseline event loop, trace buffering or message ledger.

Validation is complete. Docker was idle when the exclusive slot was released;
no further runtime runs are required. The branch retains the candidate only as
an experiment, with no production promotion.
