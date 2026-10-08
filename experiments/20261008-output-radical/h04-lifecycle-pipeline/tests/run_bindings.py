"""Executive summary: compare unchanged buffers and both journals through actual bindings."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import sysconfig
import pyarrow as pa
import pyarrow.parquet as pq

p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--corpus',type=Path,required=True)
p.add_argument('--out',type=Path,required=True);p.add_argument('--pinned',action='store_true')
a=p.parse_args();a.root=a.root.resolve();a.out=a.out.resolve();a.out.mkdir(parents=True,exist_ok=True)
tests=Path(__file__).resolve().parent
if a.pinned:
    assert sys.version_info[:2] == (3,11) and pa.__version__ == '15.0.2'
    dirs={'baseline':Path('/opt/h04-reference'),'candidate':Path('/opt/abides_fork')}
    adapter=Path('/opt')
else:
    assert platform.system()=='Darwin'
    snapshot=a.out/'reference-source'/'native';snapshot.mkdir(parents=True,exist_ok=True)
    base='ff2c1d6d3eaf4829c95c39a6032585fa9b49b7b5'
    for source in (a.root/'baselines'/'native').rglob('*'):
        if not source.is_file():continue
        rel=source.relative_to(a.root/'baselines'/'native')
        try: data=subprocess.check_output(['git','show',base+':baselines/native/'+str(rel)],cwd=a.root,stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError:continue
        target=snapshot/rel;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    # Test-only ARM log stub. It is identical for both host variants; it does not
    # alter engine arithmetic or exist in the pinned build/runtime sources.
    stub=a.out/'host-nplog.cpp';stub.write_text('namespace t3 {bool numpy_log(double,double*) {return false;} const char* numpy_log_dispatch() {return "unknown";}}\n')
    dirs={side:a.out/side/'module' for side in ['baseline','candidate']}
    lib=Path(pa.get_library_dirs()[0])
    libraries=sorted(lib.glob('libparquet.*dylib'))+sorted(lib.glob('libarrow.*dylib'))
    for side,source in [('baseline',snapshot),('candidate',a.root/'baselines'/'native')]:
        dirs[side].mkdir(parents=True,exist_ok=True)
        cmd=['c++','-std=c++20','-O2','-fno-fast-math','-ffp-contract=off','-fno-strict-aliasing','-Wall','-pthread',
             '-shared','-undefined','dynamic_lookup','-I'+str(source),'-I'+pa.get_include(),'-I'+sysconfig.get_paths()['include'],
             *[str(source/n) for n in ['module.cpp','engine.cpp','pqwrite.cpp']],str(stub),*[str(x) for x in libraries],
             '-Wl,-rpath,'+str(lib),'-o',str(dirs[side]/('_t3engine'+sysconfig.get_config_var('EXT_SUFFIX')))]
        (a.out/(side+'-build-command.json')).write_text(json.dumps(cmd,indent=2)+'\n')
        with (a.out/(side+'-build.log')).open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    adapter=a.root/'baselines'
summaries={};comparisons=[]
for side in ['baseline','candidate']:
    cmd=[sys.executable,str(tests/'extension_worker.py'),'--module-dir',str(dirs[side]),'--adapter-dir',str(adapter),
         '--corpus',str(a.corpus),'--out',str(a.out/side)]
    with (a.out/(side+'-run.log')).open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
    summaries[side]=json.loads((a.out/side/'summary.json').read_text())
assert summaries['baseline']==summaries['candidate']
for unit in ['t3-s001-price-time-priority','t3-s012-partial-fill-cancel-race']:
    for name in ['trace.parquet','message_trace.parquet']:
        l=a.out/'baseline'/unit/name;r=a.out/'candidate'/unit/name
        left=pq.read_table(l);right=pq.read_table(r)
        equal=hashlib.sha256(l.read_bytes()).hexdigest()==hashlib.sha256(r.read_bytes()).hexdigest()
        assert left.schema.equals(right.schema,check_metadata=True) and left.equals(right)
        if a.pinned:assert equal,(unit,name)
        comparisons.append({'unit':unit,'file':name,'byte_equal':equal,'schema_metadata_equal':True,'ordered_values_equal':True,
            'baseline_sha256':hashlib.sha256(l.read_bytes()).hexdigest(),'candidate_sha256':hashlib.sha256(r.read_bytes()).hexdigest()})
        if equal:
            import os
            r.unlink();os.link(l,r)
diag=json.loads((a.out/'candidate'/'diagnostics.json').read_text())
assert diag['t3-s001-price-time-priority']['encoded_while_sim_rows']==0
assert diag['t3-s012-partial-fill-cancel-race']['encoded_while_sim_rows']>0,diag
(a.out/'summary.json').write_text(json.dumps({'executive_summary':'Native bindings and both journals agree; lifecycle encoding overlaps active Sim.',
    'python':sys.version,'arrow':pa.__version__,'pinned':a.pinned,'binding':summaries,'comparisons':comparisons,'diagnostics':diag},indent=2)+'\n')
