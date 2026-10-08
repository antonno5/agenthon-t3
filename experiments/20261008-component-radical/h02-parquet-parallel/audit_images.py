"""Executive summary: audit both immutable runtime images while holding the coordinator's slot."""
import json
from pathlib import Path
import subprocess
import sys
report=Path(__file__).resolve().parent;root=report.parents[2]
docker=['docker','--context','colima-agenthon']
for side,image in [('baseline','sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c'),('candidate',sys.argv[1])]:
    out=report/'evidence/runtime-audit'/side;out.mkdir(parents=True,exist_ok=True)
    metadata=subprocess.check_output(docker+['image','inspect',image],text=True)
    (out/'image-inspect.json').write_text(metadata)
    cmd=docker+['run','--rm','--platform=linux/amd64','--network=none','--cpus=4','--memory=16g','--memory-swap=16g','--entrypoint','python',
                '-v',str(root)+':/worktree:ro','-v',str(out)+':/audit',image,
                '/worktree/experiments/20261008-component-radical/h02-parquet-parallel/runtime_audit.py']
    (out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
    subprocess.run(cmd,check=True)
