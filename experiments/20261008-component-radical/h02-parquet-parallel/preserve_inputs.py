"""Executive summary: preserve hashed diagnostic input bytes after the fixed measurements; this is not a benchmark."""
import hashlib
import json
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq
assert pa.__version__ == '15.0.2'
root=Path('/diag');record=json.loads((root/'diagnostics.json').read_text())
for key, expected in record['inputs'].items():
    unit,file=key.split('/')
    original=Path('/controls/runs')/unit/'correctness-00/baseline/retained'/file
    assert hashlib.sha256(original.read_bytes()).hexdigest()==expected['parquet_sha256']
    table=pq.read_table(original).combine_chunks()
    target=root/'inputs'/unit/('trace.arrow' if file=='trace.parquet' else 'messages.arrow')
    target.parent.mkdir(parents=True,exist_ok=True)
    with pa.OSFile(str(target),'wb') as sink:
        with pa.ipc.new_file(sink,table.schema) as writer: writer.write_table(table)
    assert hashlib.sha256(target.read_bytes()).hexdigest()==expected['ipc_sha256']
