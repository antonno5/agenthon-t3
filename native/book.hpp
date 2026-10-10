// Exchange storage: shared active-order arena, intrusive FIFO and a
// compressed binary radix price index. No price-vector shifts or FIFO scans.
#pragma once
#include <algorithm>
#include <array>
#include <cassert>
#include <cstdint>
#include <deque>
#include <limits>
#include <memory>
#include <stdexcept>
#include <vector>

namespace t3 {
struct Order {  // 40 bytes
  int64_t order_id;
  int64_t limit_price;
  int64_t quantity;
  int64_t fill_price = 0;
  int32_t agent_id;
  int8_t side;
  bool has_fill = false;
};
using BookHandle = uint32_t;
constexpr BookHandle NO_BOOK_HANDLE = std::numeric_limits<BookHandle>::max();
struct BookCounts {
  uint64_t radix_visits = 0, index_lookups = 0, fifo_unlinks = 0;
  uint64_t price_shifts = 0, fifo_scans = 0;
  void visit() {
#ifdef T3_BOOK_DIAGNOSTICS
    ++radix_visits;
#endif
  }
  void lookup() {
#ifdef T3_BOOK_DIAGNOSTICS
    ++index_lookups;
#endif
  }
  void unlink() {
#ifdef T3_BOOK_DIAGNOSTICS
    ++fifo_unlinks;
#endif
  }
};
struct ArenaOrder {
  Order order{};
  BookHandle prev = NO_BOOK_HANDLE, next = NO_BOOK_HANDLE, level = NO_BOOK_HANDLE;
  bool active = false;
};
// Native IDs are globally monotone. The directory costs one pointer per 1024
// historical IDs; full handle blocks exist only while they contain live orders.
// Slots themselves are recycled at the active-order high-water mark.
class BookArena {
  static constexpr size_t BLOCK = 1024;
  struct HandleBlock {
    std::array<BookHandle, BLOCK> handles;
    size_t active = 0;
    HandleBlock() { handles.fill(NO_BOOK_HANDLE); }
  };
  std::deque<ArenaOrder> slots_;
  std::vector<BookHandle> free_;
  std::vector<std::unique_ptr<HandleBlock>> index_;
  size_t active_ = 0;
 public:
  BookCounts counts;
  ArenaOrder& at(BookHandle h) { return slots_[h]; }
  const ArenaOrder& at(BookHandle h) const { return slots_[h]; }
  BookHandle find(int64_t oid) const {
    if (oid < 0) return NO_BOOK_HANDLE;
    const size_t block = static_cast<uint64_t>(oid) / BLOCK;
    if (block >= index_.size() || !index_[block]) return NO_BOOK_HANDLE;
    return index_[block]->handles[oid % BLOCK];
  }
  BookHandle add(const Order& order, BookHandle level) {
    if (order.order_id < 0 || find(order.order_id) != NO_BOOK_HANDLE)
      throw std::logic_error("invalid or duplicate native order ID");
    const size_t block = static_cast<uint64_t>(order.order_id) / BLOCK;
    if (block >= index_.size()) index_.resize(block + 1);
    if (!index_[block]) index_[block] = std::make_unique<HandleBlock>();
    BookHandle h;
    if (free_.empty()) {
      if (slots_.size() >= NO_BOOK_HANDLE) throw std::length_error("order arena full");
      h = static_cast<BookHandle>(slots_.size()); slots_.emplace_back();
    } else { h = free_.back(); free_.pop_back(); }
    slots_[h] = ArenaOrder{order, NO_BOOK_HANDLE, NO_BOOK_HANDLE, level, true};
    index_[block]->handles[order.order_id % BLOCK] = h;
    ++index_[block]->active; ++active_;
    return h;
  }
  void retire(BookHandle h) {
    auto& node = slots_[h];
    const auto oid = node.order.order_id;
    auto& block = index_[oid / BLOCK];
    block->handles[oid % BLOCK] = NO_BOOK_HANDLE;
    if (--block->active == 0) block.reset();
    node.active = false; free_.push_back(h); --active_;
  }
  size_t active() const { return active_; }
  size_t slot_count() const { return slots_.size(); }
  size_t directory_size() const { return index_.size(); }
  size_t live_blocks() const {
    size_t n = 0; for (const auto& b : index_) n += bool(b); return n;
  }
  // Payload/capacity estimate; allocator bookkeeping and deque maps excluded.
  size_t memory_bytes() const {
    return slots_.size() * sizeof(ArenaOrder) + free_.capacity() * sizeof(BookHandle)
      + index_.capacity() * sizeof(std::unique_ptr<HandleBlock>)
      + live_blocks() * sizeof(HandleBlock);
  }
  bool valid() const {
    size_t n = 0, indexed = 0;
    std::vector<bool> free_seen(slots_.size());
    for (auto h : free_) {
      if (h >= slots_.size() || free_seen[h] || slots_[h].active) return false;
      free_seen[h] = true;
    }
    for (size_t h = 0; h < slots_.size(); ++h) {
      const auto& o = slots_[h];
      if (o.active) { ++n; if (find(o.order.order_id) != h) return false; }
      else if (!free_seen[h]) return false;
    }
    for (size_t b = 0; b < index_.size(); ++b) if (index_[b]) {
      size_t entries = 0;
      for (size_t i = 0; i < BLOCK; ++i) {
        auto h = index_[b]->handles[i];
        if (h == NO_BOOK_HANDLE) continue;
        if (h >= slots_.size() || !slots_[h].active ||
            static_cast<uint64_t>(slots_[h].order.order_id) != b * BLOCK + i) return false;
        ++entries;
      }
      if (!entries || entries != index_[b]->active) return false;
      indexed += entries;
    }
    return n == active_ && indexed == n && n + free_.size() == slots_.size();
  }
};
struct PriceLevel {
  int64_t price = 0, total = 0;
  BookHandle head = NO_BOOK_HANDLE, tail = NO_BOOK_HANDLE;
  size_t count = 0;
  // Leaves are FIFO levels (bit=-1). Internal nodes select one differing bit.
  BookHandle child[2] = {NO_BOOK_HANDLE, NO_BOOK_HANDLE};
  BookHandle parent = NO_BOOK_HANDLE;
  int bit = -1;
};
struct BookSnapshot {
  int64_t price, total;
  std::vector<Order> orders;
};
class PriceSide {
  bool bid_;
  std::unique_ptr<BookArena> owned_;
  BookArena* arena_;
  std::vector<PriceLevel> nodes_;
  std::vector<BookHandle> free_;
  BookHandle root_ = NO_BOOK_HANDLE, best_ = NO_BOOK_HANDLE;
  size_t size_ = 0;
  static uint64_t key(int64_t p) { return static_cast<uint64_t>(p) ^ (uint64_t{1} << 63); }
  BookHandle allocate() {
    if (!free_.empty()) {
      auto h = free_.back(); free_.pop_back(); nodes_[h] = PriceLevel{}; return h;
    }
    if (nodes_.size() >= NO_BOOK_HANDLE) throw std::length_error("price arena full");
    auto h = static_cast<BookHandle>(nodes_.size()); nodes_.emplace_back(); return h;
  }
  BookHandle leaf(uint64_t k) {
    auto h = root_;
    while (h != NO_BOOK_HANDLE && nodes_[h].bit >= 0) {
      arena_->counts.visit(); h = nodes_[h].child[(k >> nodes_[h].bit) & 1];
    }
    return h;
  }
  BookHandle extreme() {
    auto h = root_;
    while (h != NO_BOOK_HANDLE && nodes_[h].bit >= 0) {
      arena_->counts.visit(); h = nodes_[h].child[bid_ ? 1 : 0];
    }
    return h;
  }
  // Recently used price levels, direct-mapped by price: new orders mostly land on a handful of
  // prices near the top, so this skips the walk down the index. A slot is trusted only while
  // it still names a live level (bit == -1) of that price; removed levels get bit -2.
  static constexpr size_t kLevelCache = 64;
  BookHandle level_cache_[kLevelCache];
  BookHandle cached_level(int64_t price) const {
    const BookHandle h = level_cache_[static_cast<uint64_t>(price) % kLevelCache];
    return h != NO_BOOK_HANDLE && h < nodes_.size() && nodes_[h].bit == -1 &&
                   nodes_[h].price == price
               ? h
               : NO_BOOK_HANDLE;
  }
  BookHandle get_level(int64_t price) {
    const BookHandle hit = cached_level(price);
    if (hit != NO_BOOK_HANDLE) return hit;
    const BookHandle h = find_or_add_level(price);
    level_cache_[static_cast<uint64_t>(price) % kLevelCache] = h;
    return h;
  }
  BookHandle find_or_add_level(int64_t price) {
    const uint64_t k = key(price);
    auto old = leaf(k);
    if (old != NO_BOOK_HANDLE && nodes_[old].price == price) return old;
    const auto fresh = allocate(); nodes_[fresh].price = price;
    if (old == NO_BOOK_HANDLE) root_ = fresh;
    else {
      const int bit = 63 - __builtin_clzll(k ^ key(nodes_[old].price));
      auto h = root_, parent = NO_BOOK_HANDLE;
      while (nodes_[h].bit > bit) {
        arena_->counts.visit(); parent = h; h = nodes_[h].child[(k >> nodes_[h].bit) & 1];
      }
      const auto branch = allocate();
      auto& b = nodes_[branch]; b.bit = bit; b.parent = parent;
      const unsigned direction = (k >> bit) & 1;
      b.child[direction] = fresh; b.child[1 - direction] = h;
      nodes_[fresh].parent = branch; nodes_[h].parent = branch;
      if (parent == NO_BOOK_HANDLE) root_ = branch;
      else nodes_[parent].child[(k >> nodes_[parent].bit) & 1] = branch;
    }
    ++size_;
    if (best_ == NO_BOOK_HANDLE || (bid_ ? price > nodes_[best_].price : price < nodes_[best_].price))
      best_ = fresh;
    return fresh;
  }
  void remove_level(BookHandle h) {
    auto parent = nodes_[h].parent;
    if (parent == NO_BOOK_HANDLE) root_ = NO_BOOK_HANDLE;
    else {
      const auto& p = nodes_[parent];
      const auto sibling = p.child[p.child[0] == h ? 1 : 0];
      const auto grand = p.parent;
      nodes_[sibling].parent = grand;
      if (grand == NO_BOOK_HANDLE) root_ = sibling;
      else nodes_[grand].child[nodes_[grand].child[0] == parent ? 0 : 1] = sibling;
      nodes_[parent].bit = -2;
      free_.push_back(parent);
    }
    nodes_[h].bit = -2;  // no longer a live level (see cached_level)
    free_.push_back(h); --size_;
    if (best_ == h) best_ = extreme();
  }
  void unlink(BookHandle h) {
    arena_->counts.unlink();
    const auto& node = arena_->at(h); auto& l = nodes_[node.level];
    if (node.prev == NO_BOOK_HANDLE) l.head = node.next;
    else arena_->at(node.prev).next = node.next;
    if (node.next == NO_BOOK_HANDLE) l.tail = node.prev;
    else arena_->at(node.next).prev = node.prev;
    --l.count;
    const auto level = node.level;
    arena_->retire(h);
    if (!l.count) remove_level(level);
  }
  void collect(BookHandle h, std::vector<BookSnapshot>& out) const {
    if (h == NO_BOOK_HANDLE) return;
    const auto& l = nodes_[h];
    if (l.bit >= 0) {
      collect(l.child[bid_ ? 1 : 0], out); collect(l.child[bid_ ? 0 : 1], out);
    } else {
      BookSnapshot s{l.price, l.total, {}};
      for (auto o = l.head; o != NO_BOOK_HANDLE; o = arena_->at(o).next)
        s.orders.push_back(arena_->at(o).order);
      out.push_back(std::move(s));
    }
  }
 public:
  explicit PriceSide(bool bid): bid_(bid), owned_(std::make_unique<BookArena>()), arena_(owned_.get()) {
    std::fill(std::begin(level_cache_), std::end(level_cache_), NO_BOOK_HANDLE);
  }
  PriceSide(bool bid, BookArena& arena): bid_(bid), arena_(&arena) {
    std::fill(std::begin(level_cache_), std::end(level_cache_), NO_BOOK_HANDLE);
  }
  size_t size() const { return size_; }
  bool empty() const { return size_ == 0; }
  const PriceLevel& best() const { assert(!empty()); return nodes_[best_]; }
  const Order& front_order() const { return arena_->at(best().head).order; }
  void enter(const Order& order) {
    const auto level = get_level(order.limit_price);
    const auto h = arena_->add(order, level);
    auto& l = nodes_[level]; auto& node = arena_->at(h);
    node.prev = l.tail;
    if (l.tail == NO_BOOK_HANDLE) l.head = h;
    else arena_->at(l.tail).next = h;
    l.tail = h; ++l.count; l.total += order.quantity;
  }
  bool cancel(const Order& request, Order& removed) {
    arena_->counts.lookup();
    auto h = arena_->find(request.order_id);
    if (h == NO_BOOK_HANDLE) return false;
    const auto& node = arena_->at(h);
    if (request.side != node.order.side || request.limit_price != node.order.limit_price ||
        (node.order.side == 1) != bid_) return false;
    removed = node.order;
    nodes_[node.level].total -= removed.quantity;
    unlink(h); return true;
  }
  Order take_best(int64_t quantity) {
    const auto h = best().head;
    auto& node = arena_->at(h); Order result = node.order;
    result.quantity = std::min(quantity, result.quantity);
    nodes_[node.level].total -= result.quantity;
    if (result.quantity == node.order.quantity) unlink(h);
    else node.order.quantity -= result.quantity;
    return result;
  }
  std::vector<BookSnapshot> snapshot() const {
    std::vector<BookSnapshot> out; collect(root_, out); return out;
  }
  size_t memory_bytes() const {
    return nodes_.capacity() * sizeof(PriceLevel) + free_.capacity() * sizeof(BookHandle);
  }
  size_t node_slots() const { return nodes_.size(); }
  const BookArena& arena() const { return *arena_; }
  bool valid() const {
    if (empty()) {
      if (root_ != NO_BOOK_HANDLE || best_ != NO_BOOK_HANDLE || free_.size() != nodes_.size()) return false;
      std::vector<bool> seen(nodes_.size());
      for (auto h : free_) {
        if (h >= seen.size() || seen[h]) return false;
        seen[h] = true;
      }
      return true;
    }
    if (root_ == NO_BOOK_HANDLE || nodes_[root_].parent != NO_BOOK_HANDLE) return false;
    std::vector<bool> seen(nodes_.size()), orders(arena_->slot_count());
    size_t leaves = 0, internal = 0;
    auto visit = [&](auto&& self, BookHandle h, int upper_bit, uint64_t mask, uint64_t prefix) -> bool {
      if (h >= nodes_.size() || seen[h]) return false;
      seen[h] = true; const auto& l = nodes_[h];
      if (l.bit >= 0) {
        if (l.bit >= upper_bit) return false;
        ++internal;
        const auto bit = uint64_t{1} << l.bit;
        for (int d = 0; d < 2; ++d) {
          auto c = l.child[d];
          if (c >= nodes_.size() || nodes_[c].parent != h ||
              !self(self, c, l.bit, mask | bit, prefix | (d ? bit : 0))) return false;
        }
        return true;
      }
      ++leaves;
      if ((key(l.price) & mask) != prefix || !l.count || l.head == NO_BOOK_HANDLE) return false;
      int64_t sum = 0; size_t count = 0; auto prev = NO_BOOK_HANDLE;
      for (auto o = l.head; o != NO_BOOK_HANDLE; o = arena_->at(o).next) {
        if (o >= orders.size() || orders[o]) return false;
        orders[o] = true; const auto& n = arena_->at(o);
        if (!n.active || n.level != h || n.prev != prev || n.order.limit_price != l.price ||
            (n.order.side == 1) != bid_ || n.order.quantity <= 0) return false;
        sum += n.order.quantity; ++count; prev = o;
      }
      return sum == l.total && count == l.count && prev == l.tail;
    };
    if (!visit(visit, root_, 64, 0, 0) || leaves != size_ || internal + 1 != leaves) return false;
    for (auto h : free_) {
      if (h >= seen.size() || seen[h]) return false;
      seen[h] = true;
    }
    for (bool s : seen) if (!s) return false;
    auto view = snapshot();
    if (view.front().price != best().price) return false;
    for (size_t i = 1; i < view.size(); ++i)
      if (bid_ ? view[i-1].price <= view[i].price : view[i-1].price >= view[i].price) return false;
    return true;
  }
};
} // namespace t3
