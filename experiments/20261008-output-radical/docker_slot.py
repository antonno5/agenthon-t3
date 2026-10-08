"""Run a complete Docker experiment under the shared exclusive host slot.

Executive summary: builds and measurements from the two experiments must not
compete for CPU or storage. Hold this advisory lock for the entire subprocess.
Usage: python docker_slot.py -- command arg ...
"""
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
args = sys.argv[1:]
if args[:1] == ['--']:
    args = args[1:]
if not args:
    raise SystemExit('Expected a subprocess command')
with (root / 'docker-slot.lock').open('a+') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    owner = root / 'docker-slot-owner.json'
    owner.write_text(json.dumps({'command': args, 'started_unix': time.time()}, indent=2)+'\n')
    try:
        code = subprocess.call(args)
    finally:
        owner.unlink(missing_ok=True)
        fcntl.flock(lock, fcntl.LOCK_UN)
raise SystemExit(code)
