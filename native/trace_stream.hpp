// Append lifecycle output while the kernel advances. Only the current timestamp needs
// ordering: quotes first, then order id, then original agent-log order for stable ties.
#pragma once

#include "engine.hpp"
#include <algorithm>
#include <limits>
#include <stdexcept>
#include <utility>

namespace t3 {

class TraceStream {
 public:
  // Negative latency is accepted by the existing config mapper. It can move the
  // kernel backwards across agents, so retain compact rows for that guarded case.
  explicit TraceStream(bool chronological = true) : chronological_(chronological) {
    // Large initial capacity: growing these by doubling copied every column again and again
    // (~18% of a large run's CPU). Untouched capacity is never faulted in, so small runs
    // pay nothing for it.
    constexpr size_t kInitialRows = size_t{1} << 21;
    columns_.t_ns.reserve(kInitialRows);
    columns_.agent_id.reserve(kInitialRows);
    columns_.msg_type.reserve(kInitialRows);
    columns_.side.reserve(kInitialRows);
    columns_.price.reserve(kInitialRows);
    columns_.size.reserve(kInitialRows);
    columns_.order_id.reserve(kInitialRows);
  }

  void order(int64_t t, int32_t owner, int32_t agent, uint8_t type, uint8_t side,
             int64_t price, int64_t size, int64_t oid) {
    advance(t);
    pending_.push_back(Row{t, price, size, oid, pending_.size(), owner, agent, type, side});
  }

  void quote(int64_t t, uint8_t side, int64_t price, int64_t size) {
    // Exchange handler times never decrease, even when the kernel can requeue a
    // negative-latency delivery. An absent side emits nothing and keeps its slot.
    if (have_quote_time_ && t < quote_time_)
      throw std::runtime_error("quote log not time-ordered");
    advance(t);
    if (!have_quote_time_ || quote_time_ != t) {
      quote_pos_[0] = quote_pos_[1] = missing;
      quote_time_ = t;
      have_quote_time_ = true;
    }
    if (quote_pos_[side] == missing) {
      quote_pos_[side] = pending_.size();
      pending_.push_back(Row{t, price, size, -1, pending_.size(), 0, 0, TM_QUOTE_UPDATE, side});
    } else {
      Row& row = pending_[quote_pos_[side]];
      row.price = price;
      row.size = size;
    }
  }

  TraceColumns finish() {
    flush();
    return std::move(columns_);
  }

 private:
  static constexpr size_t missing = std::numeric_limits<size_t>::max();
  struct Row {
    int64_t t, price, size, oid;
    size_t ordinal;
    int32_t owner, agent;
    uint8_t type, side;
  };
  bool chronological_;
  bool have_time_ = false, have_quote_time_ = false;
  int64_t time_ = 0, quote_time_ = 0;
  size_t quote_pos_[2] = {missing, missing};
  std::vector<Row> pending_;
  // Order ids are assigned densely by this engine (zero-quantity orders leave gaps).
  // Each slot points into final msg_type columns, so later executions can demote the
  // previous retained execution without a hash table or a final classification pass.
  std::vector<size_t> last_execution_;
  TraceColumns columns_;

  void advance(int64_t t) {
    if (chronological_ && have_time_ && t != time_) {
      if (t < time_) throw std::runtime_error("lifecycle time decreased");
      flush();
      quote_pos_[0] = quote_pos_[1] = missing;
    }
    have_time_ = true;
    time_ = t;
  }

  void flush() {
    // Most timestamps hold one or two rows that already arrive in key order; only sort
    // when they do not (the key is unique per row via `ordinal`, so the result is the same).
    auto less = [](const Row& a, const Row& b) {
      if (a.t != b.t) return a.t < b.t;
      if (a.oid != b.oid) return a.oid < b.oid;
      if (a.owner != b.owner) return a.owner < b.owner;
      return a.ordinal < b.ordinal;
    };
    if (pending_.size() > 1 && !std::is_sorted(pending_.begin(), pending_.end(), less))
      std::sort(pending_.begin(), pending_.end(), less);
    for (const Row& r : pending_) {
      uint8_t type = r.type;
      if (type == TM_PARTIAL_FILL) {
        const size_t oid = static_cast<size_t>(r.oid);
        if (oid >= last_execution_.size()) last_execution_.resize(oid + 1, missing);
        size_t& previous = last_execution_[oid];
        if (previous != missing) columns_.msg_type[previous] = TM_PARTIAL_FILL;
        previous = columns_.msg_type.size();
        // This means last execution in the retained trace, not zero remaining qty.
        type = TM_ORDER_FILLED;
      }
      columns_.t_ns.push_back(r.t);
      columns_.agent_id.push_back(r.agent);
      columns_.msg_type.push_back(type);
      columns_.side.push_back(r.side);
      columns_.price.push_back(r.price);
      columns_.size.push_back(r.size);
      columns_.order_id.push_back(r.oid);
    }
    pending_.clear();
  }
};

}  // namespace t3
