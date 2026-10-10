// Append-only array whose elements never move: one reserved address range (no memory until
// used), committed in chunks as it fills. Indexing is a plain array access, and references
// stay valid across push_back (what std::deque gave, without its two-level lookup).
#pragma once

#include <sys/mman.h>

#include <cstddef>
#include <new>

namespace t3 {

template <class T, size_t kChunk = 4096>
class StableArray {
 public:
  explicit StableArray(size_t max_elems = size_t{1} << 26) {
    for (size_t n = max_elems; n >= kChunk; n /= 2) {
      void* p = mmap(nullptr, n * sizeof(T), PROT_NONE,
                     MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE, -1, 0);
      if (p != MAP_FAILED) {
        base_ = static_cast<T*>(p);
        reserved_ = n;
        return;
      }
    }
    throw std::bad_alloc();
  }
  ~StableArray() { munmap(base_, reserved_ * sizeof(T)); }
  StableArray(const StableArray&) = delete;
  StableArray& operator=(const StableArray&) = delete;

  T& operator[](size_t i) { return base_[i]; }
  const T& operator[](size_t i) const { return base_[i]; }
  size_t size() const { return size_; }
  void push_back(const T& v) {
    if (size_ == committed_) grow();
    new (base_ + size_) T(v);  // T is trivially destructible: never destroyed
    size_++;
  }
  void emplace_back() { push_back(T{}); }

 private:
  T* base_ = nullptr;
  size_t reserved_ = 0, committed_ = 0, size_ = 0;
  void grow() {
    if (committed_ + kChunk > reserved_) throw std::bad_alloc();
    if (mprotect(base_ + committed_, kChunk * sizeof(T), PROT_READ | PROT_WRITE) != 0)
      throw std::bad_alloc();
    committed_ += kChunk;
  }
};

}  // namespace t3
