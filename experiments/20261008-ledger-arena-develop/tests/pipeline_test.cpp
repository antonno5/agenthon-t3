// Executive summary: exercise bounded ownership, cancellation and error propagation.
#include "message_pipeline.hpp"
#include <cassert>
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
using namespace t3;
int main() {
  MessageColumns m;
  std::vector<size_t> offsets;
  bool closed = false;
  {
    MessagePipeline p([&](const MessageColumns& b, size_t offset) {
      assert(b.t_recv.size() == 11);
      assert(b.t_recv[0] == static_cast<int64_t>(offset));
      offsets.push_back(offset);
    }, [&] { closed = true; });
    for (int i = 0; i < 100; ++i) {
      m.t_recv.assign(11, i * 11);
      p.submit(m);
      assert(m.t_recv.empty());
    }
    p.finish();
  }
  assert(closed && offsets.size() == 100 && offsets.back() == 1089);
  // Keep writer busy until two buffers have left the producer. Third submit must wait.
  std::promise<void> release;
  auto gate = release.get_future().share();
  std::atomic<int> writes{0};
  {
    MessagePipeline p([&](const MessageColumns&, size_t) {
      ++writes; gate.wait();
    }, [] {});
    m.t_recv.assign(1, 1); p.submit(m);
    m.t_recv.assign(1, 2); p.submit(m);
    auto blocked = std::async(std::launch::async, [&] {
      m.t_recv.assign(1, 3); p.submit(m);
    });
    assert(blocked.wait_for(std::chrono::milliseconds(30)) == std::future_status::timeout);
    release.set_value(); blocked.get(); p.finish();
    assert(writes == 3);
  }
  for (bool close_error : {false, true}) {
    bool threw = false;
    try {
      MessagePipeline p([&](const MessageColumns&, size_t) {
        if (!close_error) throw std::runtime_error("write injected");
      }, [&] { if (close_error) throw std::runtime_error("close injected"); });
      m.t_recv.assign(1, 0); p.submit(m); p.finish();
    } catch (const std::runtime_error&) { threw = true; }
    assert(threw);
  }
  // Worker failure must wake a blocked producer, not leave a join deadlock.
  {
    std::promise<void> fail;
    auto gate2 = fail.get_future().share();
    MessagePipeline p([&](const MessageColumns&, size_t) {
      gate2.wait(); throw std::runtime_error("blocked producer injected");
    }, [] {});
    m.t_recv.assign(1, 0); p.submit(m);
    m.t_recv.assign(1, 0); p.submit(m);
    auto blocked = std::async(std::launch::async, [&] {
      try { m.t_recv.assign(1, 0); p.submit(m); }
      catch (const std::runtime_error&) { return true; }
      return false;
    });
    fail.set_value(); assert(blocked.get());
  }
  // Destruction on a simulation exception always joins; cancellation skips footer callback.
  std::atomic<bool> finalized{false};
  try {
    MessagePipeline p([](const MessageColumns&, size_t) {}, [&] { finalized = true; });
    m.t_recv.assign(1, 0); p.submit(m);
    throw std::runtime_error("simulation injected");
  } catch (const std::runtime_error&) {}
  assert(!finalized);
  std::cout << "pipeline ownership/backpressure/write-close errors/blocked producer/cancel: passed\n";
}
