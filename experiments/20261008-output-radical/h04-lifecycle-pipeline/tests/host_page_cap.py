"""Executive summary: isolate Arrow25's added page-row cap with a test-only source snapshot.

This probe never modifies production sources and is supporting evidence only.
Pinned Arrow15 must independently pass the unmodified strict byte test.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import pyarrow as pa
import pyarrow.parquet as pq

p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
assert pa.__version__.split('.')[0]=='25'
snapshot=a.out/'source';shutil.copytree(a.source,snapshot,dirs_exist_ok=False)
file=snapshot/'pqwrite.cpp';source=file.read_text();assert source.count('  props.disable_page_checksum();')==1
file.write_text(source.replace('  props.disable_page_checksum();','  props.max_rows_per_page(kMessageRowGroupRows);  // TEST ONLY Arrow25 cap\n  props.disable_page_checksum();'))
tests=Path(__file__).resolve().parent;lib=Path(pa.get_library_dirs()[0])
libraries=sorted(lib.glob('libparquet.*dylib'))+sorted(lib.glob('libarrow.*dylib'))
cmd=['c++','-std=c++20','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-pthread','-I'+str(snapshot),
     '-I'+pa.get_include(),str(tests/'parquet_probe.cpp'),*[str(x) for x in libraries],'-Wl,-rpath,'+str(lib),'-o',str(a.out/'probe')]
(a.out/'command.json').write_text(json.dumps(cmd,indent=2)+'\n')
with (a.out/'build.log').open('w') as log:subprocess.run(cmd,check=True,stdout=log,stderr=subprocess.STDOUT)
with (a.out/'probe.log').open('w') as log:subprocess.run([str(a.out/'probe'),str(a.out/'parquet')],check=True,stdout=log,stderr=subprocess.STDOUT)
comparisons=[]
for l in sorted((a.out/'parquet').glob('*-baseline.parquet')):
    r=l.with_name(l.name.replace('-baseline','-candidate'));lh=hashlib.sha256(l.read_bytes()).hexdigest();rh=hashlib.sha256(r.read_bytes()).hexdigest()
    assert lh==rh,l.name
    left=pq.read_table(l);right=pq.read_table(r)
    assert left.schema.equals(right.schema,check_metadata=True) and left.equals(right)
    comparisons.append({'file':l.name,'byte_equal':True,'schema_metadata_equal':True,'ordered_values_equal':True,'sha256':lh})
    import os
    r.unlink();os.link(l,r)
(a.out/'summary.json').write_text(json.dumps({'executive_summary':'All synthetic pairs match exact bytes after changing only the test-copy Arrow25 page-row cap.',
    'arrow':pa.__version__,'test_only':True,'comparisons':comparisons},indent=2)+'\n')
