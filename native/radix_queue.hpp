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

// kNonNeg: every time is >= 0, so times compare as unsigned without the sign-bit flip.
template <class E, bool kNonNeg = false>  // E has int64_t time; uint64_t k2
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
      if (run_.size() - head_ > kRunMax) spill();
      return;
    }
    const int b = bucket_of(t);
    buckets_[b].push_back(e);
    if (b == 64) high_ = true; else mask_ |= uint64_t{1} << b;
  }

  // The smallest key, without reordering anything (the queue is not empty).
  unsigned __int128 min_key() const {
    if (head_ < run_.size()) return key(run_[head_]);
    const std::vector<E>& src = buckets_[mask_ ? __builtin_ctzll(mask_) : 64];
    unsigned __int128 m = key(src[0]);
    for (size_t i = 1; i < src.size(); i++) {
      const unsigned __int128 k = key(src[i]);
      if (k < m) m = k;
    }
    return m;
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
  static constexpr size_t kRunMax = 64;
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
    if (n > 32) {  // e.g. many agents waking at one nanosecond (often pushed in order)
      if (!std::is_sorted(v.begin(), v.end(), key_asc)) std::sort(v.begin(), v.end(), key_asc);
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
  static uint64_t ukey(int64_t t) {
    return kNonNeg ? static_cast<uint64_t>(t) : static_cast<uint64_t>(t) ^ (uint64_t{1} << 63);
  }
  int bucket_of(uint64_t t) const {
    const uint64_t x = t ^ ref_;
    return x == 0 ? 0 : 64 - __builtin_clzll(x);
  }
  void clear_bucket(int b) {
    if (b == 64) high_ = false; else mask_ &= ~(uint64_t{1} << b);
  }

  // Once the run outgrows kRunMax, its upper half goes back to the buckets: a run that is not
  // being drained (CalendarQueue's far part takes the pushes below its largest entry while
  // the near part is popped) would otherwise grow without bound, each insert moving all of
  // it. Every bucket entry is at least the old run's largest, hence at least the remaining
  // run's largest; and every queued time is at least ref_ (pushes are not before the last pop).
  void spill() {
    const size_t keep = head_ + kRunMax / 2;
    for (size_t i = keep; i < run_.size(); i++) {
      const int b = bucket_of(ukey(run_[i].time));
      buckets_[b].push_back(run_[i]);
      if (b == 64) high_ = true; else mask_ |= uint64_t{1} << b;
    }
    run_.resize(keep);
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

// The kernel's event queue for radix runs: a calendar ring for the near future in front of the
// radix heap. Most entries are messages due within a few microseconds of the current time
// (latency draws); they go straight into a ring of kNear buckets of 2^kShift ns each, covering
// [current bucket, current bucket + kNear), each a small array sorted by key, in one
// contiguous block (so the ring stays in cache), with a bitmask of non-empty buckets.
// Everything later -- agents' next wake-ups -- and any entry whose bucket is full goes to the
// radix heap. pop() takes the smaller of the first non-empty bucket's head and the radix heap's
// minimum (cached; read without reordering it, so the radix heap only advances when its own
// minimum is popped and its invariant -- nothing queued before the last pop -- still holds),
// so the order is exactly the (time, k2) order. Valid when no entry is pushed before the last
// popped time (as for RadixQueue): a bucket the current time has passed is then empty.
#ifndef T3_CQ_SHIFT
#define T3_CQ_SHIFT 5
#endif
#ifndef T3_CQ_NEAR
#define T3_CQ_NEAR 64
#endif
#ifndef T3_CQ_CAP
#define T3_CQ_CAP 16
#endif
template <class E, bool kNonNeg = false>
class CalendarQueue {
 public:
  bool empty() const { return near_n_ == 0 && far_n_ == 0; }

  // The near path inline, the rest (radix heap, errors) out of line.
  __attribute__((always_inline)) void push(const E& e) {
    if (__builtin_expect(e.time < last_, 0)) refuse();
    const int64_t q = e.time >> kShift;
    if (q - q0_ < kNear) {  // q >= q0_ since e.time >= last_
      const int s = static_cast<int>(q & (kNear - 1));
      Bucket& b = bucket_[s];
      if (b.end < kCap) {
        E* v = slot_[s];
        const unsigned __int128 k = key(e);
        int i = b.end++;
        while (i > b.head && k < key(v[i - 1])) {
          v[i] = v[i - 1];
          i--;
        }
        v[i] = e;
        mask_[s >> 6] |= uint64_t{1} << (s & 63);
        near_n_++;
        return;
      }
    }
    far_push(e);
  }

  E pop() {
    if (near_n_) {
      const int s = first_from(static_cast<int>(q0_ & (kNear - 1)));
      Bucket& b = bucket_[s];
      const E& head = slot_[s][b.head];
      if (key(head) < far_min_) {
        const E e = head;
        if (++b.head == b.end) {
          b.head = b.end = 0;
          mask_[s >> 6] &= ~(uint64_t{1} << (s & 63));
        }
        near_n_--;
        advance(e.time);
        return e;
      }
    }
    const E e = far_.pop();
    far_min_ = --far_n_ ? far_.min_key() : kNone;
    advance(e.time);
    return e;
  }

 private:
  static constexpr int kShift = T3_CQ_SHIFT;  // 2^kShift ns buckets
  static constexpr int kNear = T3_CQ_NEAR;    // buckets in the ring (a multiple of 64)
  static constexpr int kWords = kNear / 64;
  static constexpr int kCap = T3_CQ_CAP;      // entries per bucket; more go to the radix heap
  static_assert(kNear % 64 == 0 && (kNear & (kNear - 1)) == 0, "ring of 64-bucket words");
  static constexpr unsigned __int128 kNone = ~static_cast<unsigned __int128>(0);
  struct Bucket {
    int head = 0, end = 0;  // slot_[s][head, end) sorted by key
  };
  Bucket bucket_[kNear];
  E slot_[kNear][kCap];
  uint64_t mask_[kWords] = {};  // bit s: bucket s holds entries
  size_t near_n_ = 0;
  // The first non-empty bucket at or after s0 in ring order (some bucket is non-empty).
  int first_from(int s0) const {
    if constexpr (kWords == 1) {
      const uint64_t m = mask_[0];
      const uint64_t rot = s0 ? (m >> s0) | (m << (64 - s0)) : m;
      return (s0 + __builtin_ctzll(rot)) & 63;
    } else {
      int w = s0 >> 6;
      uint64_t bits = mask_[w] & (~uint64_t{0} << (s0 & 63));
      while (!bits) {  // back at word s0 >> 6 last: its bits below s0 come after the rest
        w = (w + 1) & (kWords - 1);
        bits = mask_[w];
      }
      return (w << 6) | __builtin_ctzll(bits);
    }
  }
  // Bucket number and time of the last pop; before the first pop, nothing is near (the
  // initial wake-ups all go to the heap).
  int64_t q0_ = INT64_MIN / 2, last_ = INT64_MIN;
  RadixQueue<E, kNonNeg> far_;
  size_t far_n_ = 0;
  unsigned __int128 far_min_ = kNone;  // far_'s smallest key

  static unsigned __int128 key(const E& e) {
    const uint64_t t = kNonNeg ? static_cast<uint64_t>(e.time)
                               : static_cast<uint64_t>(e.time) ^ (uint64_t{1} << 63);
    return (static_cast<unsigned __int128>(t) << 64) | e.k2;
  }
  void advance(int64_t t) {
    last_ = t;
    q0_ = t >> kShift;
  }
  [[noreturn]] __attribute__((noinline, cold)) static void refuse() {
    throw std::runtime_error("event scheduled before the current time");
  }
  __attribute__((noinline)) void far_push(const E& e) {
    far_.push(e);
    far_n_++;
    const unsigned __int128 k = key(e);
    if (k < far_min_) far_min_ = k;
  }
};

}  // namespace t3
