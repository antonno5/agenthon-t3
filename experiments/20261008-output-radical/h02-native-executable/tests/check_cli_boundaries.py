"""Executive summary: validate CLI errors without running a market simulation."""
import json
import subprocess
import sys

binary, config = sys.argv[1:]
base = [binary, "simulate", "--config", config, "--out", "/tmp/unused-cli-boundary/trace.parquet", "--engine", "native"]
checks = []
for tail in (["--seed", ""], ["--seed", "not-int"], ["--seed", "-1"],
             ["--seed", "4294967296"], ["--trace-mode", "unknown"], ["--engine", "unknown"]):
    p = subprocess.run(base + tail, capture_output=True, text=True)
    assert p.returncode != 0 and not p.stdout, (tail, p.returncode, p.stdout, p.stderr)
    checks.append({"args": tail, "exit_code": p.returncode, "pass": True})
for seed in (0, 4294967295):
    p = subprocess.run([binary, "--config", config, "--seed", str(seed), "--dump-native-config"], capture_output=True, text=True)
    assert p.returncode == 0 and json.loads(p.stdout)["seed"] == seed, p.stderr
    checks.append({"seed_override": seed, "pass": True})
p = subprocess.run([binary, "--help"], capture_output=True, text=True)
assert p.returncode == 0 and "simulate --config" in p.stdout
checks.append({"help": True, "pass": True})
p = subprocess.run([binary, "simulate-batch", "--help"], capture_output=True, text=True)
assert p.returncode == 0 and "--batch-dir" in p.stdout
checks.append({"batch_dispatch_help": True, "pass": True})
print(json.dumps({"passed": True, "count": len(checks), "checks": checks}))
