"""Executive summary: bind compiled native extension to the exact candidate sources."""
import hashlib
import json
from pathlib import Path
root=Path('/src/native');out=Path('/native-output/h04-checks')
out.mkdir(exist_ok=True)
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
result={'executive_summary':'Candidate native sources and installed extension are frozen by SHA256.',
        'numeric_flags':['-fno-fast-math','-ffp-contract=off'],
        'native_source_sha256':{'baselines/native/'+str(p.relative_to(root)):digest(p) for p in sorted(root.rglob('*')) if p.is_file()},
        'extension_sha256':{p.name:digest(p) for p in Path('/native-output').glob('_t3engine*.so')}}
(out/'native-build-audit.json').write_text(json.dumps(result,indent=2)+'\n')
