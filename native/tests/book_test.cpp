// Independent ordered-map model checks both sides of the shared exchange arena.
#include "book.hpp"
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>
using namespace t3;
using Reference = std::map<int64_t, std::deque<Order>>;
void check(bool value) { if (!value) throw std::runtime_error("book invariant mismatch"); }
void equal(const Order& a, const Order& b) {
  check(a.order_id == b.order_id && a.agent_id == b.agent_id && a.side == b.side &&
        a.limit_price == b.limit_price && a.quantity == b.quantity &&
        a.has_fill == b.has_fill && a.fill_price == b.fill_price);
}
void compare(const PriceSide& side, const Reference& ref, bool bid) {
  check(side.valid() && side.size() == ref.size());
  const auto view = side.snapshot(); size_t i = 0;
  auto level = [&](const auto& entry) {
    const auto& actual = view[i++];
    check(actual.price == entry.first && actual.orders.size() == entry.second.size());
    int64_t total = 0;
    for (size_t j = 0; j < actual.orders.size(); ++j) {
      equal(actual.orders[j], entry.second[j]); total += entry.second[j].quantity;
    }
    check(actual.total == total);
  };
  if (bid) for (auto it = ref.rbegin(); it != ref.rend(); ++it) level(*it);
  else for (const auto& entry : ref) level(entry);
}
int main() {
  BookArena arena;
  PriceSide sides[]{PriceSide(false, arena), PriceSide(true, arena)};
  Reference refs[2]; std::mt19937_64 rng(71); int64_t oid = 0;
  constexpr int mutations = 80000;
  for (int k = 0; k < mutations; ++k) {
    const int which = rng() % 2; auto& side = sides[which]; auto& ref = refs[which];
    const int op = rng() % 4;
    if (op < 2 || ref.empty()) {
      int64_t price;
      switch (rng() % 6) {
        case 0: price = INT64_MAX - static_cast<int64_t>(rng() % 128); break;
        case 1: price = INT64_MIN + static_cast<int64_t>(rng() % 128); break;
        default: price = static_cast<int64_t>(rng() % 512) - 256;
      }
      Order order{oid++, static_cast<int32_t>(rng() % 8), static_cast<int8_t>(which ? 1 : -1),
                  price, 1 + static_cast<int64_t>(rng() % 30), bool(rng() % 2),
                  static_cast<int64_t>(rng() % 100)};
      side.enter(order); ref[price].push_back(order);
      order.quantity = -1; // trader snapshots cannot mutate exchange storage
    } else if (op == 2) {
      auto it = ref.begin(); std::advance(it, rng() % ref.size());
      auto& fifo = it->second; const size_t j = rng() % fifo.size();
      const Order request = fifo[j]; Order removed{};
      auto wrong = request; wrong.limit_price = request.limit_price == INT64_MAX
          ? request.limit_price - 1 : request.limit_price + 1;
      check(!side.cancel(wrong, removed));
      wrong = request; wrong.side = -wrong.side;
      check(!sides[1 - which].cancel(wrong, removed));
      check(side.cancel(request, removed)); equal(removed, request);
      fifo.erase(fifo.begin() + j); if (fifo.empty()) ref.erase(it);
      check(!side.cancel(request, removed));
    } else {
      auto it = which ? std::prev(ref.end()) : ref.begin();
      auto& fifo = it->second; const int64_t quantity = 1 + rng() % 30;
      Order expected = fifo.front(); expected.quantity = std::min(expected.quantity, quantity);
      equal(side.take_best(quantity), expected);
      fifo.front().quantity -= expected.quantity;
      if (!fifo.front().quantity) fifo.pop_front();
      if (fifo.empty()) ref.erase(it);
    }
    compare(sides[0], refs[0], false); compare(sides[1], refs[1], true);
    check(arena.valid());
    size_t live = 0;
    for (const auto& ref_side : refs) for (const auto& entry : ref_side) live += entry.second.size();
    check(live == arena.active());
  }
  for (auto& side : sides) while (!side.empty()) side.take_best(INT64_MAX);
  check(arena.active() == 0 && arena.live_blocks() == 0 && arena.valid());
  check(sides[0].valid() && sides[1].valid());
  std::cout << "PASS: 80,000 shared-arena mutations, FIFO, partial fills, cancellation, signed prices, ID recycling\n";
}
