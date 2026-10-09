// Monotone priority queue (radix heap) for the kernel's event queue.
//
// Valid only when every pushed key is >= the last popped one, which holds when no latency or
// delay is negative (the kernel then never schedules into the past). Keys are (time, k2),
// compared as (time, then k2); the buckets order by time only: bucket b > 0 holds entries
// whose time first differs from `last_` (the last popped time) in bit b-1, bucket 0 those
// equal to it. Popping takes the minimal k2 among the entries at `last_`, so the pop order is
// exactly the (time, k2) order of a binary heap. Each entry moves down O(64) buckets at most,
// in practice a few, with predictable sequential work instead of a heap's mispredicted
// comparisons.
#pragma once

#include <cstdint>
#include <stdexcept>
#include <vector>

namespace t3 {

template <class E>  // E has int64_t time; uint64_t k2
class RadixQueue {
 public:
  RadixQueue() {
    for (auto& b : buckets_) b.reserve(64);
  }
  bool empty() const { return size_ == 0; }
  size_t size() const { return size_; }

  void push(const E& e) {
    const uint64_t t = ukey(e.time);
    // Callers guarantee t >= last_ (see the class comment); refuse rather than misorder.
    if (t < last_) throw std::runtime_error("event scheduled before the current time");
    const int b = bucket_of(t);
    buckets_[b].push_back(e);
    if (b == 64) high_ = true; else mask_ |= uint64_t{1} << b;
    size_++;
  }

  E pop() {
    if (buckets_[0].empty()) refill();
    std::vector<E>& b0 = buckets_[0];
    size_t best = 0;
    for (size_t i = 1; i < b0.size(); i++)
      if (b0[i].k2 < b0[best].k2) best = i;
    const E e = b0[best];
    b0[best] = b0.back();
    b0.pop_back();
    if (b0.empty()) mask_ &= ~uint64_t{1};
    size_--;
    return e;
  }

 private:
  // 65 buckets: 0 = equal to last_, b = 1..64 = highest differing bit is b-1. Bit b of mask_
  // marks bucket b (< 64) non-empty; bucket 64 is tracked by high_.
  std::vector<E> buckets_[65];
  uint64_t mask_ = 0;
  bool high_ = false;
  uint64_t last_ = 0;
  size_t size_ = 0;

  static uint64_t ukey(int64_t t) { return static_cast<uint64_t>(t) ^ (uint64_t{1} << 63); }
  int bucket_of(uint64_t t) const {
    const uint64_t x = t ^ last_;
    return x == 0 ? 0 : 64 - __builtin_clzll(x);
  }

  // Moves the entries of the lowest non-empty bucket down, around its minimal time.
  void refill() {
    int b;
    const uint64_t m = mask_ & ~uint64_t{1};
    if (m) {
      b = __builtin_ctzll(m);
    } else {
      b = 64;  // only the top bucket can be left (high_ is set)
    }
    std::vector<E>& src = buckets_[b];
    uint64_t lo = ukey(src[0].time);
    for (size_t i = 1; i < src.size(); i++) {
      const uint64_t t = ukey(src[i].time);
      if (t < lo) lo = t;
    }
    last_ = lo;
    std::vector<E> moving;
    moving.swap(src);
    if (b == 64) high_ = false; else mask_ &= ~(uint64_t{1} << b);
    for (const E& e : moving) {
      const int nb = bucket_of(ukey(e.time));  // < b
      buckets_[nb].push_back(e);
      mask_ |= uint64_t{1} << nb;
    }
    moving.clear();
    src.swap(moving);  // keep the bucket's capacity
  }
};

}  // namespace t3
