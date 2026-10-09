# Profile-guided optimization training set

`build_executable.py` builds an instrumented `t3-native`, runs it on these synthetic scenarios
(our own configurations, not the public units) and rebuilds with the recorded profile. The
profile only steers code layout and inlining; outputs are unchanged (strict FP flags are the
same in both builds). `card.toml` beside a scenario selects the ledger-optional path.
