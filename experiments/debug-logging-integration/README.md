# DEBUG logging integration

## Executive summary

Disabled DEBUG logging now skips eager argument formatting in the standard
baseline build. The user selected the exact tested patch for `codex/develop`.
Enabled DEBUG text and simulation behavior are preserved. The experiment passed
65/65 public regressions and exact dual-trace/developer-gate checks; its local
momentum and deep-book medians improved by 6.84% and 8.64%. These preliminary
Mac/Rosetta measurements do not establish general Linux performance.

## Integrated change

`baselines/patches/debug_logging.patch` is byte-identical to implementation
`a686ac924382c03571e6a9c7cd9612abab1679ef`. It adds 65 logging-level guards in
Agent, Kernel, ExchangeAgent, TradingAgent, SparseMeanRevertingOracle and
OrderBook. The standard Dockerfile applies it sixth, after the existing five
patches. Local installation instructions use the same order.

## Verification

Reversing the five prior overlays from the frozen baseline sources, then
applying all six with `git apply`, reproduces every one of the measured image's
42 core/markets Python files byte for byte. Only the six intended files differ
from the baseline. All 22 existing callback/formatting tests pass again.
`source-check.json` records ordered commands and source hashes; `result.json`
binds the completed experiment's actual gates, independent source audit and
65/65 regression evidence to SHA-256.

No new Docker build or simulation was launched for this integration because the
main campaign owns the serial Docker slot. The saved regression results belong
to the exact measured candidate image, not to a newly rebuilt development image.
Preexisting uncommitted batch-output edits remain outside this integration.
