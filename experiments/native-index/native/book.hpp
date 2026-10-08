// Adapted from the pinned native engine; price-index algorithms ported from our
// baselines/matching/state.py. See provenance.json and LICENSE.abides.
#pragma once
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <deque>
#include <vector>

namespace t3 {
struct Order {
  int64_t order_id;
  int32_t agent_id;
  int8_t side;
  int64_t limit_price;
  int64_t quantity;
  bool has_fill = false;
  int64_t fill_price = 0;
};

struct PriceLevel {
  int64_t price = 0;
  std::deque<Order> orders;
  int64_t total = 0;

  void append(const Order& order) {
    orders.push_back(order);
    total += order.quantity;
  }
  bool cancel(int64_t oid, Order& removed) {
    for (auto it = orders.begin(); it != orders.end(); ++it) {
      if (it->order_id != oid) continue;
      removed = *it;
      total -= removed.quantity;
      orders.erase(it);
      return true;
    }
    return false;
  }
  Order take(int64_t quantity) {
    Order result = orders.front();
    result.quantity = std::min(quantity, result.quantity);
    total -= result.quantity;
    if (result.quantity == orders.front().quantity) orders.pop_front();
    else orders.front().quantity -= result.quantity;
    return result;
  }
};

// A sorted numeric key vector, head fast path, and a reusable inactive prefix.
// The level vector shares the prefix: retiring the best level shifts neither
// vector. The compaction bound is the same as the adopted Python price index.
class PriceSide {
  bool bid_;
  std::vector<PriceLevel> levels_;
  std::vector<int64_t> keys_;
  size_t start_ = 0;
  int64_t key(int64_t price) const { return bid_ ? -price : price; }
 public:
  explicit PriceSide(bool bid): bid_(bid) {}
  size_t size() const { return levels_.size() - start_; }
  bool empty() const { return size() == 0; }
  PriceLevel& operator[](size_t i) { return levels_[start_ + i]; }
  const PriceLevel& operator[](size_t i) const { return levels_[start_ + i]; }
  size_t position(int64_t price) const {
    const int64_t k = key(price);
    if (empty() || k <= keys_[start_]) return 0;
    return std::lower_bound(keys_.begin() + start_ + 1, keys_.end(), k)
           - keys_.begin() - start_;
  }
  void enter(const Order& order) {
    const int64_t k = key(order.limit_price);
    // Keep the cheap append for prices worse than the last level.
    const size_t i = empty() || k > keys_.back() ? size() : position(order.limit_price);
    if (i < size() && (*this)[i].price == order.limit_price) {
      (*this)[i].append(order);
      return;
    }
    PriceLevel level;
    level.price = order.limit_price;
    level.append(order);
    if (i == 0 && start_) {
      --start_;
      levels_[start_] = std::move(level);
      keys_[start_] = k;
    } else {
      levels_.insert(levels_.begin() + start_ + i, std::move(level));
      keys_.insert(keys_.begin() + start_ + i, k);
    }
  }
  void remove_empty(size_t i) {
    if (!(*this)[i].orders.empty()) return;
    if (i == 0) {
      levels_[start_] = PriceLevel{}; // release retired queue storage immediately
      ++start_;
    } else {
      levels_.erase(levels_.begin() + start_ + i);
      keys_.erase(keys_.begin() + start_ + i);
    }
    if (empty()) {
      levels_.clear(); keys_.clear(); start_ = 0;
    } else if (start_ >= 64 && start_ >= size()) {
      levels_.erase(levels_.begin(), levels_.begin() + start_);
      keys_.erase(keys_.begin(), keys_.begin() + start_);
      start_ = 0;
    }
  }
  bool cancel(const Order& request, Order& removed) {
    const size_t i = position(request.limit_price);
    if (i == size() || (*this)[i].price != request.limit_price ||
        !(*this)[i].cancel(request.order_id, removed)) return false;
    remove_empty(i);
    return true;
  }
  Order take_best(int64_t quantity) {
    Order result = (*this)[0].take(quantity);
    remove_empty(0);
    return result;
  }
  // Test diagnostics: not used in the measured hot path.
  size_t storage_size() const { return keys_.size(); }
  size_t discarded_prefix() const { return start_; }
  bool valid() const {
    if (keys_.size() != levels_.size() || start_ > keys_.size()) return false;
    for (size_t i = start_; i < keys_.size(); ++i) {
      if (keys_[i] != key(levels_[i].price) || levels_[i].orders.empty()) return false;
      if (i > start_ && keys_[i-1] >= keys_[i]) return false;
      int64_t sum = 0;
      for (const auto& o : levels_[i].orders) sum += o.quantity;
      if (sum != levels_[i].total) return false;
    }
    return keys_.size() <= 2 * size() + 63;
  }
};
} // namespace t3
