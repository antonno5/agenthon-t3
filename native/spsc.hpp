// Single-producer/single-consumer helpers for the kernel's helper threads.
//
// The container runs under a 4-CPU quota, so a thread that waits must not burn it: waiters
// spin briefly and then sleep on a futex. Event: a sequence counter that notify() bumps;
// wait_until(pred) returns once pred() holds, sleeping between notifications. Every state
// change a waiter depends on is published BEFORE notify(), and all of it is seq_cst, so a
// notification cannot be lost between a waiter's check and its sleep (the futex compares the
// sequence it read before checking).
#pragma once

#include <immintrin.h>
#include <linux/futex.h>
#include <sys/syscall.h>
#include <unistd.h>

#include <atomic>
#include <climits>
#include <cstdint>

namespace t3 {

class Event {
 public:
  template <class Pred>
  void wait_until(Pred pred) {
    for (int i = 0; i < 512; i++) {
      if (pred()) return;
      _mm_pause();
    }
    for (;;) {
      const uint32_t s = seq_.load();
      if (pred()) return;
      waiters_.fetch_add(1);
      syscall(SYS_futex, reinterpret_cast<uint32_t*>(&seq_), FUTEX_WAIT_PRIVATE, s, nullptr,
              nullptr, 0);
      waiters_.fetch_sub(1);
    }
  }
  void notify() {
    seq_.fetch_add(1);
    if (waiters_.load())
      syscall(SYS_futex, reinterpret_cast<uint32_t*>(&seq_), FUTEX_WAKE_PRIVATE, INT_MAX,
              nullptr, nullptr, 0);
  }

 private:
  static_assert(sizeof(std::atomic<uint32_t>) == sizeof(uint32_t), "futex word");
  alignas(64) std::atomic<uint32_t> seq_{0};
  std::atomic<uint32_t> waiters_{0};
};

}  // namespace t3
