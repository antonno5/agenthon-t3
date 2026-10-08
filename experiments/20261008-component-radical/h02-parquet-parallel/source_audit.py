"""Executive summary: audit the exact Arrow 15.0.2 source paths used for bounded column encoding."""
import hashlib
import json
from pathlib import Path
import urllib.request
root = 'https://raw.githubusercontent.com/apache/arrow/apache-arrow-15.0.2/cpp/src/'
paths = ['parquet/arrow/writer.cc', 'parquet/properties.h', 'arrow/util/parallel.h',
         'parquet/file_writer.cc', 'parquet/column_writer.cc']
files = {}
for path in paths:
    data = urllib.request.urlopen(root+path, timeout=30).read()
    files[path] = {'url': root+path, 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    text = data.decode()
    if path == 'parquet/arrow/writer.cc':
        assert 'arrow_properties_->executor()' in text and 'parallel_column_write_contexts_' in text
        table = text[text.index('Status WriteTable('):text.index('Status NewBufferedRowGroup()')]
        assert 'NewRowGroup(size)' in table and 'WriteColumnChunk' in table and 'ParallelFor' not in table
    if path == 'parquet/properties.h':
        assert 'DEFAULT_WRITE_BATCH_SIZE = 1024' in text
        assert 'Builder* set_use_threads(bool use_threads)' in text
        assert 'Builder* set_executor(::arrow::internal::Executor* executor)' in text
    if path == 'arrow/util/parallel.h':
        assert 'executor->Submit(func, i)' in text and 'st &= fut.status()' in text
record = {'executive_summary': 'Arrow 15.0.2 parallelizes only buffered RecordBatch columns. A shared two-worker executor keeps both writers within the four-CPU single-market budget.',
          'tag': 'apache-arrow-15.0.2', 'sources': files,
          'findings': [
              'WriteTable calls NewRowGroup and writes column chunks serially even with use_threads enabled.',
              'WriteRecordBatch prepares distinct column writers/contexts and calls ParallelFor with the configured executor.',
              'ParallelFor submits all column tasks and awaits every future status before returning normal task errors. Input array/OwnedBuffers storage therefore outlives tasks.',
              'No caller or pipeline dispatcher is scheduled inside the encoder executor; the nested-executor deadlock warned about in properties.h is avoided.',
              'Buffered row group column writers keep independent state; row-group Close serializes column writers in schema order.',
              'Dense UTF8 and integers still use progressive encoder dictionaries; no dictionary array or precomputed vocabulary is introduced.',
              'Dictionary page limit, data page limit, write_batch_size=1024, 64Mi property maximum and actual 1Mi groups remain unchanged.',
              'Pending column tasks are bounded by at most two synchronous writer calls times 7/10 columns; three ledger buffers and existing backpressure remain unchanged.'
          ],
          'limitations': ['Pool creation/shutdown infrastructure failures are not fault-injected.',
                          'Single market caller contract: pool capacity is shared process-wide but unrelated concurrent run_write callers are outside the frozen runner contract.',
                          'Host Arrow25 checks are preliminary; pinned Arrow15 byte checks remain required.']}
Path(__file__).with_name('source-audit.json').write_text(json.dumps(record, indent=2)+'\n')
