"""Executive summary: reproducible host/pinned focused checks; no scenario timing."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import pyarrow as pa
import pyarrow.parquet as pq

p = argparse.ArgumentParser()
p.add_argument('--source',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--pinned',action='store_true')
a = p.parse_args(); a.out.mkdir(parents=True,exist_ok=True)
if a.pinned:
    assert sys.version_info[:2] == (3,11) and pa.__version__ == '15.0.2'
tests=Path(__file__).resolve().parent
common=['c++','-std=c++17' if a.pinned else '-std=c++20','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-pthread','-I'+str(a.source)]
records=[]
def run(cmd,label):
    with (a.out/(label+'.log')).open('w') as log:
        result=subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT)
    records.append({'command':cmd,'exit_code':result.returncode,'log':label+'.log'})
    (a.out/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
    assert result.returncode == 0, (label,result.returncode)
for name in ['trace_test','pipeline_test']:
    run(common+[str(tests/(name+'.cpp')),'-o',str(a.out/name)],name+'-build')
    run([str(a.out/name)],name)
    if not a.pinned:
        run(common+['-fsanitize=address,undefined','-fno-omit-frame-pointer',str(tests/(name+'.cpp')),
                    '-o',str(a.out/(name+'-asan'))],name+'-asan-build')
        run([str(a.out/(name+'-asan'))],name+'-asan')
lib=Path(pa.get_library_dirs()[0]); libraries=sorted(lib.glob('libparquet.*dylib'))+sorted(lib.glob('libarrow.*dylib'))
links=[str(x) for x in libraries] if platform.system() == 'Darwin' else ['-L'+str(lib),'-l:libparquet.so.1500','-l:libarrow.so.1500']
run(common+['-I'+pa.get_include(),str(tests/'parquet_probe.cpp')]+links+['-Wl,-rpath,'+str(lib),'-o',str(a.out/'parquet_probe')],'parquet-build')
run([str(a.out/'parquet_probe'),str(a.out/'parquet')],'parquet-probe')
comparisons=[]
for left in sorted((a.out/'parquet').glob('*-baseline.parquet')):
    right=left.with_name(left.name.replace('-baseline','-candidate'))
    l=pq.ParquetFile(left);r=pq.ParquetFile(right)
    lh=hashlib.sha256(left.read_bytes()).hexdigest();rh=hashlib.sha256(right.read_bytes()).hexdigest()
    equal=lh == rh
    assert l.schema_arrow.equals(r.schema_arrow,check_metadata=True),left.name
    assert l.read().equals(r.read()),left.name
    assert [l.metadata.row_group(i).num_rows for i in range(l.num_row_groups)] == [r.metadata.row_group(i).num_rows for i in range(r.num_row_groups)]
    if a.pinned: assert equal,left.name
    comparisons.append({'file':left.name,'byte_equal':equal,'schema_metadata_equal':True,'ordered_values_equal':True,
                        'baseline_sha256':lh,'candidate_sha256':rh})
    if equal:
        # Keep one physical copy of identical evidence.
        import os
        right.unlink();os.link(left,right)
summary={'executive_summary':'Focused ownership, late mutation, fallback, overlap and Parquet boundaries passed.',
         'python':sys.version,'arrow':pa.__version__,'pinned':a.pinned,'commands':records,'comparisons':comparisons}
(a.out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
