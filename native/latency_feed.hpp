// The kernel's message latencies come from one dedicated RandomState whose draws do not depend
// on the market state: the n-th send (sender != recipient) always takes the n-th draw. A
// producer thread therefore computes them ahead -- the same code on its own copy of the RNG,
// so the values are identical -- and the kernel only reads the next one from a ring of chunks.
#pragma once

#include <atomic>
#include <cstdint>
#include <memory>
#include <thread>

#include "spsc.hpp"

namespace t3 {

class LatencyFeed {
 public:
  LatencyFeed() = default;
  LatencyFeed(const LatencyFeed&) = delete;
  LatencyFeed& operator=(const LatencyFeed&) = delete;
  ~LatencyFeed() { stop(); }

  template <class Draw>
  void start(Draw draw) {
    ring_.reset(new int64_t[kChunks * kChunkVals]);
    worker_ = std::thread([this, draw]() mutable {
      for (size_t head = 0;; head++) {
        space_.wait_until([&] { return stop_.load() || head - consumed_.load() < kChunks; });
        if (stop_.load()) return;
        int64_t* chunk = ring_.get() + (head % kChunks) * kChunkVals;
        for (size_t i = 0; i < kChunkVals; i++) chunk[i] = draw();
        published_.store(head + 1);
        data_.notify();
      }
    });
    active_ = true;
  }
  bool active() const { return active_; }

  int64_t next() {
    if (pos_ == kChunkVals) refill();
    return cur_[pos_++];
  }

 private:
  static constexpr size_t kChunkVals = 8192;
  static constexpr size_t kChunks = 8;
  std::unique_ptr<int64_t[]> ring_;
  const int64_t* cur_ = nullptr;
  size_t pos_ = kChunkVals;
  size_t tail_ = 0;  // chunks taken by the kernel
  bool active_ = false;
  alignas(64) std::atomic<size_t> published_{0};
  alignas(64) std::atomic<size_t> consumed_{0};
  std::atomic<bool> stop_{false};
  Event data_, space_;
  std::thread worker_;

  void refill() {
    if (tail_ > 0) {  // release the chunk just used up
      consumed_.store(tail_);
      space_.notify();
    }
    data_.wait_until([this] { return published_.load() > tail_; });
    cur_ = ring_.get() + (tail_ % kChunks) * kChunkVals;
    tail_++;
    pos_ = 0;
  }
  void stop() {
    if (!worker_.joinable()) return;
    stop_.store(true);
    space_.notify();
    worker_.join();
  }
};

}  // namespace t3
