"""Executive summary: add identical diagnostic clocks to disposable copies of both writers."""
def replace(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)

def instrument(source):
    pipeline = (source/'message_pipeline.hpp').read_text()
    pipeline = replace(pipeline, '#include <thread>', '#include <thread>\n#include <chrono>')
    pipeline = replace(pipeline, '  using Write =', '''  double producer_wait_seconds = 0, dispatcher_idle_seconds = 0;
  size_t submit_count = 0;
  using Write =''')
    pipeline = replace(pipeline,
        '    changed_.wait(lock, [this] { return error_ || stopped_ || !free_.empty(); });',
        '''    auto wait_begin = std::chrono::steady_clock::now();
    changed_.wait(lock, [this] { return error_ || stopped_ || !free_.empty(); });
    producer_wait_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now()-wait_begin).count();
    ++submit_count;''')
    pipeline = replace(pipeline,
        '          changed_.wait(lock, [this] { return stopped_ || !pending_.empty(); });',
        '''          auto idle_begin = std::chrono::steady_clock::now();
          changed_.wait(lock, [this] { return stopped_ || !pending_.empty(); });
          dispatcher_idle_seconds += std::chrono::duration<double>(std::chrono::steady_clock::now()-idle_begin).count();''')
    (source/'message_pipeline.hpp').write_text(pipeline)
    module = (source/'module.cpp').read_text()
    module = replace(module, '  double seconds = 0;', '''  double seconds = 0, producer_wait = 0, ledger_write = 0, ledger_close = 0;
  double trace_write = 0, finish_wait = 0, dispatcher_idle = 0;
  size_t callbacks = 0, submits = 0;''')
    module = replace(module, '          writer->append(block, offset);', '''          auto callback_begin = std::chrono::steady_clock::now();
          writer->append(block, offset);
          ledger_write += std::chrono::duration<double>(std::chrono::steady_clock::now()-callback_begin).count();
          ++callbacks;''')
    module = replace(module, '          writer->close();', '''          auto close_begin = std::chrono::steady_clock::now();
          writer->close();
          ledger_close += std::chrono::duration<double>(std::chrono::steady_clock::now()-close_begin).count();''')
    module = replace(module, '      t3::write_trace(r.trace, trace_path);\n      pipeline.finish();', '''      auto trace_begin = std::chrono::steady_clock::now();
      t3::write_trace(r.trace, trace_path);
      trace_write = std::chrono::duration<double>(std::chrono::steady_clock::now()-trace_begin).count();
      auto finish_begin = std::chrono::steady_clock::now();
      pipeline.finish();
      finish_wait = std::chrono::duration<double>(std::chrono::steady_clock::now()-finish_begin).count();
      producer_wait = pipeline.producer_wait_seconds;
      dispatcher_idle = pipeline.dispatcher_idle_seconds;
      submits = pipeline.submit_count;''')
    module = replace(module,
        '  return Py_BuildValue("(nnd)", static_cast<Py_ssize_t>(r.trace.t_ns.size()),\n                       static_cast<Py_ssize_t>(r.n_messages), seconds);',
        '''  return Py_BuildValue("(nndddddddnn)", static_cast<Py_ssize_t>(r.trace.t_ns.size()),
                       static_cast<Py_ssize_t>(r.n_messages), seconds, producer_wait,
                       ledger_write, ledger_close, trace_write, finish_wait, dispatcher_idle,
                       static_cast<Py_ssize_t>(callbacks), static_cast<Py_ssize_t>(submits));''')
    (source/'module.cpp').write_text(module)
