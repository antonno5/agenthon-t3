"""Executive summary: retain all validated sample paths with identical bytes while deduplicating storage."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
report=Path(__file__).resolve().parent;root=report.parents[2];evidence=report/'evidence'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
objects=evidence/'objects/parquet';objects.mkdir(parents=True,exist_ok=True)
entries=[];original_total=0;unique_total=0
# Only closed, validated own outputs are touched. Verify every source before
# replacing an equal-byte path with its canonical hardlink.
for path in sorted(evidence.rglob('*.parquet')):
    if objects in path.parents: continue
    digest=sha(path); size=path.stat().st_size;original_total+=size
    canonical=objects/(digest+'.parquet')
    if not canonical.exists(): os.link(path,canonical);unique_total+=size
    else:
        assert canonical.stat().st_size==size and sha(canonical)==digest
        if path.stat().st_ino!=canonical.stat().st_ino:
            temporary=path.with_name(path.name+'.dedup-link');os.link(canonical,temporary);os.replace(temporary,path)
    entries.append({'path':str(path.relative_to(evidence)),'sha256_before_dedup':digest,'bytes':size,'object':str(canonical.relative_to(evidence))})
record=json.loads((evidence/'diagnostics/run/diagnostics.json').read_text())
assert record['complete'] and len(record['samples'])==192
restored=[]
for sample in record['samples']:
    target=evidence/'diagnostics/run/samples'/sample['unit']/sample['mode']/f"{sample['kind']}-{sample['pair']:02d}"/sample['side']
    for file,digest in sample['sha256'].items():
        original=evidence/'controls/runs'/sample['unit']/'correctness-00/baseline/retained'/file
        assert sha(original)==digest and sample['byte_equal_to_real_baseline']
        path=target/file
        if not path.exists(): os.link(original,path)
        assert sha(path)==digest
        restored.append({'sample_path':str(path.relative_to(evidence)),'original_sample_sha256':digest,
                         'validated_equal_control':str(original.relative_to(evidence)),
                         'storage':'hardlink of validated identical control bytes after original sample digest comparison'})
# Preserve uncompressed IPC inputs with the same pinned serializer and verify
# the already recorded input digests. No simulation or measurement is repeated.
docker=['docker','--context','colima-agenthon']
cmd=docker+['run','--rm','--platform=linux/amd64','--network=none','--cpus=4','--memory=16g','--memory-swap=16g','--entrypoint','python',
 '-v',str(root)+':/worktree:ro','-v',str(evidence/'controls')+':/controls:ro','-v',str(evidence/'diagnostics/run')+':/diag',
 'sha256:0bace6e254c0ecf48b5a598e6001ff79fda062f1de81bf003d151ae51510b36c',
 '/worktree/experiments/20261008-component-radical/h02-parquet-parallel/preserve_inputs.py']
subprocess.run(cmd,check=True)
manifest={'executive_summary':'Every closed Parquet path is retained with independently verified bytes; redundant storage uses hardlinks. Diagnostic sample outputs and IPC inputs are preserved after their original digest comparisons.',
 'existing_paths':entries,'diagnostic_output_paths':restored,'input_preservation_command':cmd,
 'pre_dedup_logical_bytes':original_total,'new_canonical_bytes':unique_total,
 'source_scope':'Only this H2 worktree evidence, after its fixed measurements completed.'}
(evidence/'storage-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'parquet_paths':len(entries),'diagnostic_output_paths':len(restored),'logical_bytes':original_total,'canonical_bytes':unique_total}))
