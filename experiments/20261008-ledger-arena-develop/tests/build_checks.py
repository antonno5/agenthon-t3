"""Executive summary: build and check pipeline and rowgroup boundaries on Arrow15."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import pyarrow
import pyarrow.parquet as pq

assert sys.version_info[:2] == (3,11)
assert pyarrow.__version__ == '15.0.2'
lib=pyarrow.get_library_dirs()[0]
source=Path('/src/native'); tests=Path('/src/h02-tests'); out=Path('/native-output/h02-checks')
out.mkdir(exist_ok=True)
common=['g++','-std=c++17','-O2','-fno-fast-math','-ffp-contract=off','-Wall','-pthread','-I'+str(source)]
subprocess.run(common+[str(tests/'pipeline_test.cpp'),'-o',str(out/'pipeline_test')],check=True)
subprocess.run([str(out/'pipeline_test')],check=True)
subprocess.run(common+['-I'+pyarrow.get_include(),str(tests/'parquet_probe.cpp'),str(source/'engine.cpp'),
                      '-L'+lib,'-l:libparquet.so.1500','-l:libarrow.so.1500','-Wl,-rpath,'+lib,
                      '-o',str(out/'parquet_probe')],check=True)
subprocess.run([str(out/'parquet_probe'),str(out/'parquet-probe')],check=True)
comparisons=[]
for p in sorted((out/'parquet-probe').glob('*-table.parquet')):
    n=int(p.name.split('-')[0]);left=pq.ParquetFile(p)
    for variant in ['candidate','partial']:
        other=p.with_name(p.name.replace('-table','-'+variant));right=pq.ParquetFile(other)
        assert hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(other.read_bytes()).digest(),(n,variant)
        assert left.schema_arrow.equals(right.schema_arrow,check_metadata=True)
        assert left.read().equals(right.read())
        assert [right.metadata.row_group(i).num_rows for i in range(right.num_row_groups)] == [min(1048576,n-i) for i in range(0,n,1048576)]
        comparisons.append({'rows':n,'variant':variant,'byte_equal':True,'schema_equal':True,'semantic_exact_equal':True})
(out/'pinned-build-checks.json').write_text(json.dumps({'executive_summary':'Pinned synthetic pipeline and rowgroup checks passed.',
    'python':sys.version,'arrow':pyarrow.__version__,'comparisons':comparisons},indent=2)+'\n')

audit={'executive_summary':'Compiled native source hashes and extension digests for immutable installed-source auditing.',
       'numeric_flags':['-fno-fast-math','-ffp-contract=off'],
       'native_source_sha256':{'baselines/native/'+str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest()
                                for p in sorted(source.rglob('*')) if p.is_file()},
       'extension_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in Path('/native-output').glob('_t3engine*.so')}}
(out/'native-build-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
