// Monotone priority queue (radix heap) for the kernel's event queue.
//
// Valid only when every pushed key is >= the last popped one, which holds when no latency or
// delay is negative (the kernel then never schedules into the past). Keys are (time, k2),
// compared as (time, then k2).
//
// Buckets order by time relative to a reference `ref_` (<= every queued time): bucket 0 holds
// times equal to it, bucket b > 0 times whose highest bit differing from it is b-1, so every
// entry of a lower non-empty bucket is smaller than every entry of a higher one. Pops drain
// `run_`, the smallest entries sorted by ascending key, from `head_` on. When the run is
// empty, the lowest non-empty bucket becomes the next run: sorted whole when it is small,
// otherwise first spread over the buckets below it around its minimum, which becomes the new
// reference (higher buckets stay valid: the new reference agrees with the old one on every bit
// above the spread bucket). A push smaller than the run's largest entry is inserted into the
// run, any other goes to its bucket, so the pop order is exactly the (time, k2) order of a
// binary heap. Sorting small buckets instead of spreading them saves most entry moves: near-term
// messages arrive in small groups, and many agents share wake-up times (every noise trader of
// a scenario wakes at the same nanosecond).
#pragma once

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <vector>

#ifndef T3_RQ_MAXBIT
#define T3_RQ_MAXBIT 10
#endif

namespace t3 {

template <class E>  // E has int64_t time; uint64_t k2
class RadixQueue {
 public:
  RadixQueue() {
    for (auto& b : buckets_) b.reserve(64);
    run_.reserve(256);
  }
  bool empty() const { return size_ == 0; }
  size_t size() const { return size_; }

  void push(const E& e) {
    const uint64_t t = ukey(e.time);
    // Callers guarantee t >= the last popped time (see the class comment); refuse rather
    // than misorder.
    if (t < last_) throw std::runtime_error("event scheduled before the current time");
    size_++;
    if (head_ < run_.size() && key(e) < key(run_.back())) {  // below the run's largest entry
      run_.insert(std::upper_bound(run_.begin() + head_, run_.end(), e, key_asc), e);
      return;
    }
    const int b = bucket_of(t);
    buckets_[b].push_back(e);
    if (b == 64) high_ = true; else mask_ |= uint64_t{1} << b;
  }

  E pop() {
    if (head_ == run_.size()) refill();
    const E e = run_[head_++];
    size_--;
    last_ = ukey(e.time);
    return e;
  }

 private:
  // A bucket is sorted whole when it is small and spans little time (below 2^kSortMaxBit ns):
  // a run keeps taking the pushes below its largest entry, so it must not reach far ahead.
  static constexpr size_t kSortWhole = 32;
  static constexpr int kSortMaxBit = T3_RQ_MAXBIT;
  // 65 buckets: bit b of mask_ marks bucket b (< 64) non-empty; bucket 64 is tracked by high_.
  std::vector<E> buckets_[65];
  std::vector<E> run_;  // the smallest entries, by ascending key; [head_, end) not yet popped
  size_t head_ = 0;
  uint64_t mask_ = 0;
  bool high_ = false;
  uint64_t ref_ = 0;   // bucket reference
  uint64_t last_ = 0;  // last popped time
  size_t size_ = 0;

  // (time, k2) as one unsigned 128-bit integer: a single wide compare instead of two branches.
  static unsigned __int128 key(const E& e) {
    return (static_cast<unsigned __int128>(ukey(e.time)) << 64) | e.k2;
  }
  static bool key_asc(const E& a, const E& b) { return key(a) < key(b); }
  // Ascending insertion sort: buckets fill mostly in time order, so it is close to linear
  // (a descending sort of the same input was quadratic).
  static void sort_asc(std::vector<E>& v) {
    const size_t n = v.size();
    if (n > 32) {  // e.g. many agents waking at one nanosecond, in no particular order
      std::sort(v.begin(), v.end(), key_asc);
      return;
    }
    for (size_t i = 1; i < n; i++) {
      const E x = v[i];
      const unsigned __int128 kx = key(x);
      if (!(kx < key(v[i - 1]))) continue;
      size_t j = i;
      for (; j > 0 && kx < key(v[j - 1]); j--) v[j] = v[j - 1];
      v[j] = x;
    }
  }
  static uint64_t ukey(int64_t t) { return static_cast<uint64_t>(t) ^ (uint64_t{1} << 63); }
  int bucket_of(uint64_t t) const {
    const uint64_t x = t ^ ref_;
    return x == 0 ? 0 : 64 - __builtin_clzll(x);
  }
  void clear_bucket(int b) {
    if (b == 64) high_ = false; else mask_ &= ~(uint64_t{1} << b);
  }

  // Makes the lowest non-empty bucket the run (the queue is not empty, the run is).
  void refill() {
    for (;;) {
      const int b = mask_ ? __builtin_ctzll(mask_) : 64;  // else only bucket 64 is left
      std::vector<E>& src = buckets_[b];
      if (b == 0 || (b <= kSortMaxBit && src.size() <= kSortWhole)) {
        run_.clear();
        head_ = 0;
        run_.swap(src);  // the bucket keeps the run's emptied buffer
        clear_bucket(b);
        if (run_.size() > 1) sort_asc(run_);
        return;
      }
      uint64_t lo = ukey(src[0].time);
      for (size_t i = 1; i < src.size(); i++) {
        const uint64_t t = ukey(src[i].time);
        if (t < lo) lo = t;
      }
      ref_ = lo;
      std::vector<E> moving;
      moving.swap(src);
      clear_bucket(b);
      for (const E& e : moving) {
        const int nb = bucket_of(ukey(e.time));  // < b
        buckets_[nb].push_back(e);
        mask_ |= uint64_t{1} << nb;
      }
      moving.clear();
      src.swap(moving);  // keep the bucket's capacity
    }
  }
};

}  // namespace t3
