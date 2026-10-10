// See engine.hpp. Comments cite the Python they mirror (file:function) so each step can be
// checked against the reference.
#include "engine.hpp"
#include "book.hpp"
#include "latency_feed.hpp"
#include "output_log.hpp"
#include "radix_queue.hpp"
#include "trace_stream.hpp"

#include <algorithm>
#include <cmath>
#include <deque>
#include <memory>
#include <limits>
#include <stdexcept>
#include <unordered_map>

namespace t3 {

const char* const kMsgTypeNames[MT_COUNT] = {
    "AGENT_WAKEUP",          "MarketClosePriceRequestMsg", "MarketHoursRequestMsg",
    "MarketHoursMsg",        "QuerySpreadMsg",             "QuerySpreadResponseMsg",
    "LimitOrderMsg",         "CancelOrderMsg",             "OrderAcceptedMsg",
    "OrderExecutedMsg",      "OrderCancelledMsg",          "MarketClosedMsg",
    "MarketClosePriceMsg",
};

namespace {

// ------------------------------------------------------------------------------------------
// Python numeric semantics helpers
// ------------------------------------------------------------------------------------------

// Python's round(float) -> int: round-half-to-even (the default FE_TONEAREST mode).
inline int64_t py_round(double x) {
  if (!std::isfinite(x)) throw std::runtime_error("round() of non-finite value");
  return static_cast<int64_t>(std::nearbyint(x));
}

// float ** 2 in CPython calls libm pow(); keep GCC from folding pow(x, 2.0) into x*x.
double (*volatile libm_pow)(double, double) = &::pow;

// A Python number that is either an int or a float (the oracle's time stamps switch from
// int to float once a megashock time -- int + float -- enters the series).
struct Num {
  bool is_float;
  int64_t i;
  double f;
  static Num of_int(int64_t v) { return Num{false, v, 0.0}; }
  static Num of_float(double v) { return Num{true, 0, v}; }
  double as_double() const { return is_float ? f : static_cast<double>(i); }
};

// Exact three-way comparison of an int with a float, as CPython does it (no rounding of
// the int to float). Returns -1, 0, 1, or 2 for unordered (NaN).
int cmp_int_float(int64_t a, double b) {
  if (std::isnan(b)) return 2;
  if (b >= 9223372036854775808.0) return -1;
  if (b < -9223372036854775808.0) return 1;
  const double fl = std::floor(b);
  const int64_t bi = static_cast<int64_t>(fl);
  if (a < bi) return -1;
  if (a > bi) return 1;
  return (b > fl) ? -1 : 0;
}

int cmp(const Num& a, const Num& b) {
  if (!a.is_float && !b.is_float) return (a.i < b.i) ? -1 : (a.i > b.i ? 1 : 0);
  if (a.is_float && b.is_float) {
    if (std::isnan(a.f) || std::isnan(b.f)) return 2;
    return (a.f < b.f) ? -1 : (a.f > b.f ? 1 : 0);
  }
  if (!a.is_float) return cmp_int_float(a.i, b.f);
  const int c = cmp_int_float(b.i, a.f);
  return c == 2 ? 2 : -c;
}
inline bool lt(const Num& a, const Num& b) { return cmp(a, b) == -1; }
inline bool le(const Num& a, const Num& b) {
  const int c = cmp(a, b);
  return c == -1 || c == 0;
}
inline bool ge(const Num& a, const Num& b) {
  const int c = cmp(a, b);
  return c == 1 || c == 0;
}

// a - b with Python int/float promotion.
Num sub(const Num& a, const Num& b) {
  if (!a.is_float && !b.is_float) return Num::of_int(a.i - b.i);
  return Num::of_float(a.as_double() - b.as_double());
}

// Python floor division for ints.
inline int64_t floordiv(int64_t a, int64_t b) {
  int64_t q = a / b;
  if ((a % b != 0) && ((a < 0) != (b < 0))) --q;
  return q;
}

// ------------------------------------------------------------------------------------------
// Orders and messages
// ------------------------------------------------------------------------------------------

constexpr int8_t BID = 1, ASK = -1;

struct Message {
  int64_t id;
  uint8_t type;
  int32_t refs = 0;  // pending deliveries (heap entries); the slot is recycled at 0
  Order order{};  // LimitOrder / CancelOrder / OrderAccepted / OrderExecuted / OrderCancelled
  // QuerySpreadResponseMsg (depth 1)
  bool has_bid = false, has_ask = false, mkt_closed = false;
  int64_t bid_p = 0, bid_q = 0, ask_p = 0, ask_q = 0;
  bool has_order() const {
    return type == MT_LIMIT_ORDER || type == MT_CANCEL_ORDER || type == MT_ORDER_ACCEPTED ||
           type == MT_ORDER_EXECUTED || type == MT_ORDER_CANCELLED;
  }
};

// Heap entry; the Python heap item is (time, (sender_id, recipient_id, message)) and
// messages compare by message_id, so (time, sender, recipient, message_id) is the order.
// Message storage: fixed-size blocks, never moved once allocated, so references held by a
// handler stay valid while it creates new messages (the property std::deque gave us) --
// with plain shift/mask indexing instead of deque iterator arithmetic.
class MessageSlab {
 public:
  // Recycled slots are reused last-freed-first, so nearly every live slot is in the first
  // block: one load instead of two.
  Message& operator[](size_t i) {
    return i < kBlock ? first_[i] : blocks_[i >> kShift][i & kMask];
  }
  const Message& operator[](size_t i) const {
    return i < kBlock ? first_[i] : blocks_[i >> kShift][i & kMask];
  }
  size_t size() const { return size_; }
  void push_back(const Message& m) {
    if ((size_ & kMask) == 0) {
      blocks_.emplace_back(new Message[kBlock]);
      if (!first_) first_ = blocks_[0].get();
    }
    (*this)[size_++] = m;
  }

 private:
  static constexpr size_t kShift = 12, kBlock = size_t{1} << kShift, kMask = kBlock - 1;
  std::vector<std::unique_ptr<Message[]>> blocks_;
  Message* first_ = nullptr;
  size_t size_ = 0;
};

// Heap entry, 32 bytes. The Python heap item is (time, (sender_id, recipient_id, message))
// and messages compare by message_id, so the order is (time, sender, recipient, message_id);
// agent ids are non-negative, so (sender, recipient) compares as one unsigned 64-bit route.
// The send-time ledger fields live in Sim::send_info (index `info`, -1 for wakeups, whose
// ledger row is built on delivery): the Python ledger row is fixed at send time, and a
// requeue moves `time` but not the recorded t_recv.
struct QEntry {
  int64_t time;
  uint64_t route;  // (sender << 32) | recipient
  int64_t msg_id;
  int32_t slot;    // index into Sim::msgs
  int32_t info;    // index into Sim::send_info, -1 for wakeups
  int32_t sender() const { return static_cast<int32_t>(route >> 32); }
  int32_t recipient() const { return static_cast<int32_t>(route & 0xffffffffu); }
  static uint64_t make_route(int32_t sender, int32_t recipient) {
    return (static_cast<uint64_t>(static_cast<uint32_t>(sender)) << 32) |
           static_cast<uint32_t>(recipient);
  }
  bool operator>(const QEntry& o) const {
    if (time != o.time) return time > o.time;
    if (route != o.route) return route > o.route;
    return msg_id > o.msg_id;
  }
};

// Compact heap entry for runs with < 2^16 agents and < 2^32 messages (every realistic run):
// (sender:16 | recipient:16 | msg_id:32) orders exactly like (sender, recipient, msg_id), so
// the whole key is (time, k2) and compares as one 128-bit integer. 24 bytes instead of 32.
struct PackedEntry {
  int64_t time;
  uint64_t k2;
  int32_t slot, info;
  unsigned __int128 key() const {
    return (static_cast<unsigned __int128>(static_cast<uint64_t>(time) ^ (uint64_t{1} << 63))
            << 64) | k2;
  }
};

struct SendInfo {
  int64_t t_send, t_recv, causal;  // causal < 0: None
};


// ------------------------------------------------------------------------------------------
// Simulation
// ------------------------------------------------------------------------------------------

class Sim;

// TradingAgent.orders: a dict keyed by order id. This engine hands out order ids in ascending
// order, so a trader's open orders arrive already sorted: they live in a flat vector (append on
// insert, a tombstone on erase, compacted once half are dead) that iterates in the dict's
// insertion order without a node allocation per order. Lookups go through `pos`, shared by all
// traders: order id -> index in its owner's vector (-1 once erased).
class OpenOrders {
 public:
  void insert(const Order& o, std::vector<int32_t>& pos) {  // o.order_id exceeds every earlier id
    const size_t id = static_cast<size_t>(o.order_id);
    if (id >= pos.size()) pos.resize(std::max(id + 1, 2 * pos.size()), -1);
    pos[id] = static_cast<int32_t>(v_.size());
    v_.push_back(o);
    dead_.push_back(0);
  }
  Order* find(int64_t id, const std::vector<int32_t>& pos) {
    if (id < 0 || static_cast<size_t>(id) >= pos.size()) return nullptr;
    const int32_t i = pos[static_cast<size_t>(id)];
    if (i < 0 || static_cast<size_t>(i) >= v_.size() || v_[i].order_id != id || dead_[i])
      return nullptr;
    return &v_[i];
  }
  void erase(Order* o, std::vector<int32_t>& pos) {
    pos[static_cast<size_t>(o->order_id)] = -1;
    dead_[static_cast<size_t>(o - v_.data())] = 1;
    if (++n_dead_ >= 16 && 2 * n_dead_ >= v_.size()) compact(pos);
  }
  template <class F>
  void for_each(F f) const {
    for (size_t i = 0; i < v_.size(); i++)
      if (!dead_[i]) f(v_[i]);
  }

 private:
  std::vector<Order> v_;
  std::vector<uint8_t> dead_;
  size_t n_dead_ = 0;
  void compact(std::vector<int32_t>& pos) {
    size_t k = 0;
    for (size_t i = 0; i < v_.size(); i++)
      if (!dead_[i]) {
        v_[k] = v_[i];
        pos[static_cast<size_t>(v_[k].order_id)] = static_cast<int32_t>(k);
        k++;
      }
    v_.resize(k);
    dead_.assign(k, 0);
    n_dead_ = 0;
  }
};

struct Trader {
  int32_t id;
  AgentParams p;
  RandomState rs;
  int64_t current_time = 0;
  bool have_hours = false;
  int64_t mkt_open = 0, mkt_close = 0;
  bool mkt_closed = false, first_wake = true;
  bool awaiting_spread = false;
  bool kb = false, ka = false;  // known_bids / known_asks non-empty
  int64_t kb_p = 0, kb_q = 0, ka_p = 0, ka_q = 0;
  OpenOrders orders;
  std::vector<double> mid_hist;
};

class Sim {
 public:
  explicit Sim(Params p, MessageSink* sink, TraceSink* trace_sink)
      : P(std::move(p)),
        out(P.lat_min >= 0 && P.lat_max >= 0 && P.default_delay >= 0 &&
                P.pipeline_delay >= 0 && P.computation_delay >= 0,
            sink, trace_sink, P.ledger) {}
  Result run();

 private:
  Params P;
  // kernel
  int64_t current_time = 0;
  std::vector<int64_t> agent_times, comp_delays;
  std::vector<QEntry> heap;
  std::vector<PackedEntry> pheap;
  CalendarQueue<PackedEntry> rqueue;
  bool packed = false;  // pheap (or rqueue) in use (see PackedEntry)
  bool radix = false;   // rqueue in use: packed keys and no negative latency/delay
  // Deliveries waiting for a busy agent (radix runs only; see Sim::defer). waiting[r] is a
  // min-heap by (route, msg_id); the queue holds one stand-in entry for it (slot kStandIn,
  // info = its generation), keyed like the heap's smallest entry. A newer stand-in makes the
  // older ones stale (their generation no longer matches waiting_gen[r]).
  static constexpr int32_t kStandIn = -2;
  std::vector<std::vector<QEntry>> waiting;
  std::vector<int32_t> waiting_gen;
  std::vector<SendInfo> send_info;
  std::vector<int32_t> free_info;
  // deque: handlers hold references to the message being delivered while creating new
  // ones, and push_back on a deque never invalidates references to existing elements.
  MessageSlab msgs;
  std::vector<int32_t> free_slots;  // recycled message slots
  size_t n_messages = 0;
  bool has_causal = false;
  int64_t causal = 0;
  int64_t next_msg_id = 1;
  int64_t next_order_id = 0;
  // RNGs
  RandomState global_rs, oracle_rs, latency_rs;
  // oracle
  Num r_t{false, 0, 0.0};
  int64_t r_v = 0;
  double ms_time = 0, ms_value = 0;  // last megashock (time is always a float)
  // exchange (agent 0)
  int64_t ex_time = 0;
  BookArena exchange_orders;
  PriceSide bids{true, exchange_orders}, asks{false, exchange_orders};
  bool has_last_trade = true;
  int64_t last_trade = 0;
  std::vector<int32_t> close_price_subs;
  OutputLog out;  // trace + ledger, built on its own thread in call order
  // traders (agent ids 1..n)
  std::vector<Trader> traders;
  std::vector<int32_t> order_pos;  // order id -> index in its trader's OpenOrders

  // --- kernel ---
  int32_t new_msg(uint8_t type) {
    if (packed && next_msg_id > 0xffffffffll)
      throw std::runtime_error("message id exceeds the packed heap key");
    // A recycled slot keeps its old payload: every reader only looks at the fields its
    // message type's creator sets (order for order messages, the spread fields for
    // QuerySpreadResponseMsg), so only the header is reset.
    int32_t slot;
    if (!free_slots.empty()) {
      slot = free_slots.back();
      free_slots.pop_back();
    } else {
      msgs.push_back(Message{});
      slot = static_cast<int32_t>(msgs.size() - 1);
    }
    Message& m = msgs[slot];
    m.id = next_msg_id++;
    m.type = type;
    m.refs = 0;
    return slot;
  }
  void release(int32_t slot) {
    if (--msgs[slot].refs == 0) free_slots.push_back(slot);
  }
  void deliver_row(int64_t msg_id, int32_t src, int32_t dst, bool has_send, int64_t t_send,
                   int64_t t_recv, uint8_t type, bool has_oid, int64_t oid, int64_t causal_v) {
    if (P.ledger) out.deliver(msg_id, src, dst, has_send, t_send, t_recv, type, has_oid, oid, causal_v);
    ++n_messages;
  }
  // 4-ary min-heap on QEntry's total order (keys are unique: msg_id is unique per message and
  // route separates a shared message's recipients), so it pops exactly the sequence the
  // binary std:: heap -- and Python's heapq -- would; it is shallower and touches fewer
  // cache lines per pop.
  template <class E, class Greater>
  static void heap_push_impl(std::vector<E>& h, const E& e, Greater gt) {
    size_t i = h.size();
    h.push_back(e);
    while (i > 0) {
      const size_t parent = (i - 1) >> 2;
      if (!gt(h[parent], e)) break;
      h[i] = h[parent];
      i = parent;
    }
    h[i] = e;
  }
  template <class E, class Greater>
  static E heap_pop_impl(std::vector<E>& h, Greater gt) {
    const E top = h[0];
    const E last = h.back();
    h.pop_back();
    const size_t n = h.size();
    if (n > 0) {
      size_t i = 0;
      while (true) {
        const size_t c = (i << 2) + 1;
        if (c >= n) break;
        size_t best = c;
        const size_t end = std::min(c + 4, n);
        for (size_t k = c + 1; k < end; k++)
          if (gt(h[best], h[k])) best = k;
        if (!gt(last, h[best])) break;
        h[i] = h[best];
        i = best;
      }
      h[i] = last;
    }
    return top;
  }
  static bool packed_gt(const PackedEntry& a, const PackedEntry& b) { return a.key() > b.key(); }
  static bool full_gt(const QEntry& a, const QEntry& b) { return a > b; }
  bool heap_empty() const {
    return radix ? rqueue.empty() : packed ? pheap.empty() : heap.empty();
  }
  void heap_push(const QEntry& e) {
    if (packed) {
      const uint64_t k2 = (static_cast<uint64_t>(e.sender()) << 48) |
                          (static_cast<uint64_t>(e.recipient()) << 32) |
                          static_cast<uint64_t>(e.msg_id);
      if (radix)
        rqueue.push(PackedEntry{e.time, k2, e.slot, e.info});
      else
        heap_push_impl(pheap, PackedEntry{e.time, k2, e.slot, e.info}, packed_gt);
    } else {
      heap_push_impl(heap, e, full_gt);
    }
  }
  QEntry heap_pop() {
    if (packed) {
      const PackedEntry p = radix ? rqueue.pop() : heap_pop_impl(pheap, packed_gt);
      return QEntry{p.time, QEntry::make_route(static_cast<int32_t>(p.k2 >> 48),
                                               static_cast<int32_t>((p.k2 >> 32) & 0xffff)),
                    static_cast<int64_t>(p.k2 & 0xffffffffu), p.slot, p.info};
    }
    return heap_pop_impl(heap, full_gt);
  }
  // ScenarioLatencyModel.get_latency: one draw per message between distinct agents.
  struct LatencyDraw {
    int model;
    double mu, sigma, lo, hi, alpha, mean;
    RandomState rs;
    int64_t operator()() {
      double value;
      switch (model) {
        case LAT_LOGNORMAL: value = rs.lognormal(mu, sigma); break;
        case LAT_UNIFORM: value = rs.uniform(lo, hi); break;
        case LAT_PARETO: {
          const double base = lo > 0 ? lo : 1.0;
          value = base * (1.0 + rs.pareto(alpha));
          break;
        }
        default: value = mean;
      }
      double c = (lo > value) ? lo : value;  // max(value, min_ns)
      c = (hi < c) ? hi : c;                  // min(.., max_ns)
      return py_round(c);
    }
  };
  LatencyFeed latency_feed;  // draws computed ahead on a helper thread
  int64_t constant_latency = 0;
  int64_t latency(int32_t s, int32_t r) {
    if (s == r) return 0;
    return latency_feed.active() ? latency_feed.next() : constant_latency;
  }
  // Kernel.send_message (+ ExchangeAgent.send_message's pipeline delay via `delay`)
  void send(int32_t sender, int32_t recipient, int32_t slot, int64_t delay = 0) {
    const int64_t sent_time = current_time + comp_delays[sender] + delay;
    const int64_t deliver_at = sent_time + latency(sender, recipient);
    Message& m = msgs[slot];
    m.refs++;
    int32_t info = 0;  // the send-time ledger fields, kept only for a ledger
    if (P.ledger) {
      const SendInfo si{sent_time, deliver_at, has_causal ? causal : -1};
      if (!free_info.empty()) {
        info = free_info.back();
        free_info.pop_back();
        send_info[info] = si;
      } else {
        info = static_cast<int32_t>(send_info.size());
        send_info.push_back(si);
      }
    }
    heap_push(QEntry{deliver_at, QEntry::make_route(sender, recipient), m.id, slot, info});
  }
  // Kernel.runner requeues a delivery whose recipient is still busy (agent_times[r] after its
  // time) at agent_times[r]; while that agent stays busy, each of its other pending deliveries
  // is requeued again on every pop -- quadratic in a burst. Those pops change nothing but
  // current_time, so a radix run parks the deliveries instead and keeps one stand-in in the
  // queue with the smallest parked key: it pops exactly where that delivery's own requeue
  // would, and the order of every processed delivery stays the same (all parked deliveries of
  // r end up at the same time, agent_times[r], and leave by key). Near stop_time the plain
  // requeue is kept, so the loop ends after the same pop.
  static bool waiting_gt(const QEntry& a, const QEntry& b) {
    return a.route != b.route ? a.route > b.route : a.msg_id > b.msg_id;
  }
  void push_stand_in(int32_t r) {
    const QEntry& top = waiting[r].front();
    heap_push(QEntry{agent_times[r], top.route, top.msg_id, kStandIn, ++waiting_gen[r]});
  }
  // Parks e (recipient r busy, agent_times[r] <= stop_time).
  void defer(const QEntry& e, int32_t r) {
    std::vector<QEntry>& w = waiting[r];
    const bool smallest = w.empty() || waiting_gt(w.front(), e);
    w.push_back(e);
    std::push_heap(w.begin(), w.end(), waiting_gt);
    if (smallest) push_stand_in(r);
  }
  // The parked deliveries go back into the queue at agent_times[r] as plain requeues.
  void unpark(int32_t r) {
    for (QEntry re : waiting[r]) {
      re.time = agent_times[r];
      heap_push(re);
    }
    waiting[r].clear();
    ++waiting_gen[r];
  }
  // After r handled a delivery taken from its parked set.
  void repark(int32_t r) {
    if (waiting[r].empty()) return;
    if (agent_times[r] > P.stop_time)
      unpark(r);
    else
      push_stand_in(r);
  }

  // Kernel.set_wakeup
  void set_wakeup(int32_t agent, int64_t t) {
    if (current_time != 0 && t < current_time)
      throw std::runtime_error("set_wakeup() called with requested time not in future");
    // A wake-up carries nothing but its message id, so it takes no message slot (slot -1).
    if (packed && next_msg_id > 0xffffffffll)
      throw std::runtime_error("message id exceeds the packed heap key");
    heap_push(QEntry{t, QEntry::make_route(agent, agent), next_msg_id++, -1, -1});
  }

  // --- oracle (SparseMeanRevertingOracle) ---
  int64_t compute_fundamental(const Num& ts, double v_adj, bool adj_is_float, const Num& pt,
                              int64_t pv);
  int64_t advance(const Num& t);
  int64_t observe(int64_t t, RandomState& rs, double sigma_n);

  // --- exchange ---
  void exchange_wakeup(int64_t t);
  void exchange_receive(int64_t t, int32_t sender, int32_t slot);
  void handle_limit_order(Order order);
  bool cancel_order(const Order& order);
  bool execute_order(Order& order, int64_t& matched_qty, int64_t& matched_price);
  void enter_order(const Order& order);
  void log_best() {
    if (!bids.empty()) out.quote(ex_time, SIDE_BID, bids.best().price, bids.best().total);
    if (!asks.empty()) out.quote(ex_time, SIDE_ASK, asks.best().price, asks.best().total);
  }
  void ex_send(int32_t recipient, int32_t slot) {
    const uint8_t t = msgs[slot].type;
    const bool pipeline =
        (t == MT_ORDER_ACCEPTED || t == MT_ORDER_CANCELLED || t == MT_ORDER_EXECUTED);
    send(0, recipient, slot, pipeline ? P.pipeline_delay : 0);
  }

  // --- traders ---
  Trader& trader(int32_t id) { return traders[id - 1]; }
  void trader_wakeup(Trader& a, int64_t t);
  void trader_receive(Trader& a, int64_t t, int32_t slot);
  void act(Trader& a);
  void place_limit_order(Trader& a, int64_t qty, int8_t side, int64_t price);

  void log_order(const Trader& a, int64_t t, uint8_t type, const Order& o) {
    out.order(t, a.id, o.agent_id, type, o.side == BID ? SIDE_BID : SIDE_ASK,
                type == TM_PARTIAL_FILL ? (o.has_fill ? o.fill_price : 0) : o.limit_price,
                o.quantity, o.order_id);
  }
  Result extract();
};

// ------------------------------------------------------------------------------------------
// Oracle
// ------------------------------------------------------------------------------------------

// sparse_mean_reverting_oracle.compute_fundamental_at_timestamp
int64_t Sim::compute_fundamental(const Num& ts, double v_adj, bool adj_is_float, const Num& pt,
                                 int64_t pv) {
  const Num d = sub(ts, pt);
  const double dd = d.as_double();
  const double mu = static_cast<double>(P.r_bar);
  const double gamma = P.kappa;
  const double theta = P.fund_vol;
  // loc = mu + (pv - mu) * exp(-gamma * d)
  const double loc =
      mu + static_cast<double>(pv - P.r_bar) * std::exp((-gamma) * dd);
  // scale = sqrt(((theta**2) / (2 * gamma)) * (1 - exp(-2 * gamma * d)))
  const double scale =
      std::sqrt((libm_pow(theta, 2.0) / (2.0 * gamma)) * (1.0 - std::exp((-2.0 * gamma) * dd)));
  // numpy rejects scale < 0; a NaN scale passes and yields NaN, which max(0, v) maps to 0.
  if (scale < 0) throw std::runtime_error("oracle normal scale < 0");
  double v = oracle_rs.normal(loc, scale);
  if (adj_is_float) v += v_adj;  // `v += 0` (int) leaves the float unchanged too
  v = (v > 0) ? v : 0.0;         // max(0, v)
  int64_t vi = py_round(v);
  for (Jump& j : P.jumps) {
    if (!j.consumed && ge(ts, Num::of_int(j.time_ns))) {
      vi = std::max<int64_t>(0, vi + j.magnitude);
      j.consumed = true;
    }
  }
  r_t = ts;
  r_v = vi;
  return vi;
}

// advance_fundamental_value_series
int64_t Sim::advance(const Num& t) {
  Num pt = r_t;
  int64_t pv = r_v;
  if (le(t, pt)) return pv;
  double mst = ms_time, msv = ms_value;
  while (lt(Num::of_float(mst), t)) {
    const int64_t v = compute_fundamental(Num::of_float(mst), msv, true, pt, pv);
    pt = Num::of_float(mst);
    pv = v;
    // mst = pt + int(np.random.exponential(scale=1.0 / lambda))
    const double e = global_rs.exponential(1.0 / P.megashock_lambda_a);
    if (!std::isfinite(e)) throw std::runtime_error("megashock interval not finite");
    mst = pt.f + std::trunc(e);
    msv = oracle_rs.normal(P.megashock_mean, std::sqrt(P.megashock_var));
    msv = (oracle_rs.randint(0, 2) == 0) ? msv : -msv;
    ms_time = mst;
    ms_value = msv;
  }
  return compute_fundamental(t, 0.0, false, pt, pv);
}

// observe_price
int64_t Sim::observe(int64_t t, RandomState& rs, double sigma_n) {
  const int64_t r = (t >= P.oracle_close) ? advance(Num::of_int(P.oracle_close - 1))
                                           : advance(Num::of_int(t));
  if (sigma_n == 0) return r;
  return py_round(rs.normal(static_cast<double>(r), std::sqrt(sigma_n)));
}

// ------------------------------------------------------------------------------------------
// Exchange + order book
// ------------------------------------------------------------------------------------------

// ExchangeAgent.wakeup
void Sim::exchange_wakeup(int64_t t) {
  ex_time = t;
  if (t >= P.mkt_close) {
    const int32_t slot = new_msg(MT_MKT_CLOSE_PRICE);  // one message, many recipients
    for (int32_t a : close_price_subs) ex_send(a, slot);
    if (close_price_subs.empty()) free_slots.push_back(slot);
  }
}

// ExchangeAgent.receive_message
void Sim::exchange_receive(int64_t t, int32_t sender, int32_t slot) {
  ex_time = t;
  comp_delays[0] = P.computation_delay;  // set_computation_delay(self.computation_delay)
  const uint8_t type = msgs[slot].type;
  if (t > P.mkt_close) {
    if (type != MT_QUERY_SPREAD) {  // OrderMsg and every non-query -> MarketClosedMsg
      ex_send(sender, new_msg(MT_MKT_CLOSED));
      return;
    }
  }
  switch (type) {
    case MT_MKT_HOURS_REQ: {
      comp_delays[0] = 0;
      ex_send(sender, new_msg(MT_MKT_HOURS));
      break;
    }
    case MT_MKT_CLOSE_PRICE_REQ:
      close_price_subs.push_back(sender);
      break;
    case MT_QUERY_SPREAD: {
      const int32_t r = new_msg(MT_QUERY_SPREAD_RESP);
      Message& m = msgs[r];
      m.has_bid = m.has_ask = false;
      m.bid_p = m.bid_q = m.ask_p = m.ask_q = 0;
      // get_l2_bid_data(depth=1): first level if its visible total > 0
      if (!bids.empty() && bids.best().total > 0) {
        m.has_bid = true;
        m.bid_p = bids.best().price;
        m.bid_q = bids.best().total;
      }
      if (!asks.empty() && asks.best().total > 0) {
        m.has_ask = true;
        m.ask_p = asks.best().price;
        m.ask_q = asks.best().total;
      }
      m.mkt_closed = t > P.mkt_close;
      ex_send(sender, r);
      break;
    }
    case MT_LIMIT_ORDER:
      handle_limit_order(msgs[slot].order);  // deepcopy(message.order)
      break;
    case MT_CANCEL_ORDER:
      cancel_order(msgs[slot].order);
      break;
    default:
      throw std::runtime_error("exchange received an unexpected message type");
  }
}

// OrderBook.enter_order (no PTC / hidden / insert_by_id orders on this path)
void Sim::enter_order(const Order& order) {
  PriceSide& book = order.side == BID ? bids : asks;
  book.enter(order);
}

bool Sim::cancel_order(const Order& order) {
  PriceSide& book = order.side == BID ? bids : asks;
  Order cancelled;
  if (!book.cancel(order, cancelled)) return false;
  const int32_t slot = new_msg(MT_ORDER_CANCELLED);
  msgs[slot].order = cancelled;
  ex_send(order.agent_id, slot);
  return true;
}

// OrderBook.execute_order. Returns false for "None" (no match).
bool Sim::execute_order(Order& order, int64_t& matched_qty, int64_t& matched_price) {
  PriceSide& book = order.side == BID ? asks : bids;
  if (book.empty()) return false;
  const PriceLevel& lvl = book.best();
  const bool match = order.side == BID ? order.limit_price >= lvl.price
                                       : order.limit_price <= lvl.price;
  if (!match) return false;
  Order matched = book.take_best(order.quantity);
  matched.has_fill = true;
  matched.fill_price = matched.limit_price;
  Order filled = order;
  filled.quantity = matched.quantity;
  filled.has_fill = true;
  filled.fill_price = matched.fill_price;
  order.quantity -= filled.quantity;
  int32_t s1 = new_msg(MT_ORDER_EXECUTED);
  msgs[s1].order = matched;
  ex_send(matched.agent_id, s1);
  int32_t s2 = new_msg(MT_ORDER_EXECUTED);
  msgs[s2].order = filled;
  ex_send(order.agent_id, s2);
  matched_qty = matched.quantity;
  matched_price = matched.fill_price;
  return true;
}

// OrderBook.handle_limit_order (quiet=False)
void Sim::handle_limit_order(Order order) {
  if (order.quantity <= 0 || order.limit_price < 0) return;  // discarded with a warning
  int64_t trade_qty = 0;
  bool executed_any = false;
  int64_t trade_price_i = 0;
  while (true) {
    if (P.stp != STP_NONE) {
      PriceSide& opp = order.side == BID ? asks : bids;
      if (!opp.empty()) {
        const bool m = order.side == BID ? order.limit_price >= opp.best().price
                                         : order.limit_price <= opp.best().price;
        if (m) {
          const Order resting = opp.front_order();
          if (resting.agent_id == order.agent_id) {
            if (P.stp == STP_CANCEL_OLDEST && cancel_order(resting)) continue;
            if (P.stp != STP_CANCEL_OLDEST) {
              const int32_t slot = new_msg(MT_ORDER_CANCELLED);
              msgs[slot].order = order;
              ex_send(order.agent_id, slot);
              break;
            }
          }
        }
      }
    }
    int64_t q, p;
    if (execute_order(order, q, p)) {
      executed_any = true;
      trade_qty += q;
      trade_price_i += p * q;
      if (order.quantity <= 0) break;
    } else {
      enter_order(order);
      const int32_t slot = new_msg(MT_ORDER_ACCEPTED);
      msgs[slot].order = order;
      ex_send(order.agent_id, slot);
      break;
    }
  }
  log_best();
  if (executed_any) {
    // avg_price = int(round(trade_price / trade_qty)) -- int/int true division
    last_trade = py_round(static_cast<double>(trade_price_i) / static_cast<double>(trade_qty));
    has_last_trade = true;
  }
}

// ------------------------------------------------------------------------------------------
// Traders (TradingAgent + abides_fork.agents.ScheduledAgent subclasses)
// ------------------------------------------------------------------------------------------

void Sim::place_limit_order(Trader& a, int64_t qty, int8_t side, int64_t price) {
  Order o;
  o.order_id = next_order_id++;  // LimitOrder() takes an id even if then ignored
  o.agent_id = a.id;
  o.side = side;
  o.limit_price = price;
  o.quantity = qty;
  if (qty <= 0) return;  // "ignored limit order of quantity zero"
  a.orders.insert(o, order_pos);
  const int32_t slot = new_msg(MT_LIMIT_ORDER);
  msgs[slot].order = o;
  send(a.id, 0, slot);
  log_order(a, a.current_time, TM_ORDER_SUBMITTED, o);
}

void Sim::trader_wakeup(Trader& a, int64_t t) {
  a.current_time = t;
  // TradingAgent.wakeup
  if (a.first_wake) {
    a.first_wake = false;
    send(a.id, 0, new_msg(MT_MKT_CLOSE_PRICE_REQ));
  }
  if (!a.have_hours) send(a.id, 0, new_msg(MT_MKT_HOURS_REQ));
  // ScheduledAgent.wakeup
  if (!a.have_hours || a.mkt_open == 0 || a.mkt_close == 0 || a.mkt_closed) return;
  set_wakeup(a.id, t + a.p.interval);
  const int32_t q = new_msg(MT_QUERY_SPREAD);
  send(a.id, 0, q);
  a.awaiting_spread = true;
}

void Sim::trader_receive(Trader& a, int64_t t, int32_t slot) {
  a.current_time = t;
  const Message& m = msgs[slot];
  const bool had_hours = a.have_hours;
  switch (m.type) {
    case MT_MKT_HOURS:
      a.have_hours = true;
      a.mkt_open = P.mkt_open;
      a.mkt_close = P.mkt_close;
      break;
    case MT_MKT_CLOSE_PRICE:
      break;  // last_trade only feeds mark_to_market
    case MT_MKT_CLOSED:
      a.mkt_closed = true;
      break;
    case MT_ORDER_EXECUTED: {
      log_order(a, t, TM_PARTIAL_FILL, m.order);
      if (Order* o = a.orders.find(m.order.order_id, order_pos)) {
        if (m.order.quantity >= o->quantity)
          a.orders.erase(o, order_pos);
        else
          o->quantity -= m.order.quantity;
      }
      break;
    }
    case MT_ORDER_ACCEPTED:
      log_order(a, t, TM_ORDER_ACCEPTED, m.order);
      break;
    case MT_ORDER_CANCELLED:
      log_order(a, t, TM_ORDER_CANCELLED, m.order);
      if (Order* o = a.orders.find(m.order.order_id, order_pos)) a.orders.erase(o, order_pos);
      break;
    case MT_QUERY_SPREAD_RESP:
      if (m.mkt_closed) a.mkt_closed = true;
      a.kb = m.has_bid;
      a.kb_p = m.bid_p;
      a.kb_q = m.bid_q;
      a.ka = m.has_ask;
      a.ka_p = m.ask_p;
      a.ka_q = m.ask_q;
      break;
    default:
      throw std::runtime_error("trader received an unexpected message type");
  }
  if (a.have_hours && !had_hours) set_wakeup(a.id, a.mkt_open + 0);
  // ScheduledAgent.receive_message
  if (a.awaiting_spread && m.type == MT_QUERY_SPREAD_RESP) {
    if (!a.mkt_closed) act(a);
    a.awaiting_spread = false;
  }
}

void Sim::act(Trader& a) {
  // get_known_bid_ask: None when the side is empty; Python truthiness also treats 0 as false.
  const bool bid = a.kb && a.kb_p != 0;
  const bool ask = a.ka && a.ka_p != 0;
  const int64_t bp = a.kb_p, ap = a.ka_p;
  switch (a.p.kind) {
    case NOISE: {
      const double draw = a.rs.normal(a.p.d0, a.p.d1);
      const int64_t size = std::max<int64_t>(1, py_round(draw));
      const bool buy = a.rs.randint(0, 2) != 0;
      const int64_t offset = a.rs.randint(0, a.p.i0 + 1);
      if (buy) {
        const int64_t anchor = ask ? ap : (bid ? bp : a.p.i1);
        place_limit_order(a, size, BID, anchor + offset);
      } else {
        const int64_t anchor = bid ? bp : (ask ? ap : a.p.i1);
        place_limit_order(a, size, ASK, anchor - offset);
      }
      break;
    }
    case MARKET_MAKER: {
      const int64_t mid = (bid && ask) ? floordiv(bp + ap, 2) : a.p.i3;
      // cancel_all_orders: iterate self.orders.values() (insertion order)
      a.orders.for_each([&](const Order& o) {
        const int32_t slot = new_msg(MT_CANCEL_ORDER);
        msgs[slot].order = o;
        send(a.id, 0, slot);
      });
      const int64_t half = floordiv(a.p.i0, 2);
      for (int64_t lvl = 0; lvl < a.p.i1; lvl++) {
        place_limit_order(a, a.p.i2, BID, mid - half - lvl);
        place_limit_order(a, a.p.i2, ASK, mid + half + lvl);
      }
      break;
    }
    case VALUE: {
      double mid;
      if (bid && ask)
        mid = static_cast<double>(bp + ap) / 2.0;
      else if (bid)
        mid = static_cast<double>(bp);
      else if (ask)
        mid = static_cast<double>(ap);
      else
        return;
      const int64_t fundamental = observe(a.current_time, a.rs, a.p.d0);
      const int64_t size = a.p.i0, thr = a.p.i1;
      if (mid < static_cast<double>(fundamental - thr) && ask)
        place_limit_order(a, size, BID, ap);
      else if (mid > static_cast<double>(fundamental + thr) && bid)
        place_limit_order(a, size, ASK, bp);
      break;
    }
    case MOMENTUM: {
      double mid;
      if (bid && ask)
        mid = static_cast<double>(bp + ap) / 2.0;
      else if (bid)
        mid = static_cast<double>(bp);
      else if (ask)
        mid = static_cast<double>(ap);
      else
        return;
      const int64_t lookback = a.p.i2;
      a.mid_hist.push_back(mid);
      if (static_cast<int64_t>(a.mid_hist.size()) > lookback + 1)
        a.mid_hist.erase(a.mid_hist.begin());
      if (static_cast<int64_t>(a.mid_hist.size()) <= lookback) return;
      const double past = a.mid_hist[0];
      const int64_t size = a.p.i0, thr = a.p.i1;
      if (mid > past + static_cast<double>(thr) && ask)
        place_limit_order(a, size, BID, ap);
      else if (mid < past - static_cast<double>(thr) && bid)
        place_limit_order(a, size, ASK, bp);
      break;
    }
    default:
      throw std::runtime_error("unknown agent kind");
  }
}

// ------------------------------------------------------------------------------------------
// Run
// ------------------------------------------------------------------------------------------

Result Sim::run() {
  const int32_t n_agents = static_cast<int32_t>(P.agents.size()) + 1;
  // --- abides_fork.config.build_config: global RNG draw order ---
  global_rs.seed(P.seed);
  oracle_rs.seed(global_rs.randint_u32_full());
  // SparseMeanRevertingOracle.__init__
  {
    const double delta = global_rs.exponential(1.0 / P.megashock_lambda_a);
    ms_time = static_cast<double>(P.mkt_open) + delta;
    double msv = oracle_rs.normal(P.megashock_mean, std::sqrt(P.megashock_var));
    ms_value = (oracle_rs.randint(0, 2) == 0) ? msv : -msv;
    r_t = Num::of_int(P.mkt_open);
    r_v = P.r_bar;
  }
  (void)global_rs.randint_u32_full();  // ExchangeAgent random_state (unused on this path)
  traders.reserve(P.agents.size());
  for (size_t i = 0; i < P.agents.size(); i++) {
    Trader t;
    t.id = static_cast<int32_t>(i + 1);
    t.p = P.agents[i];
    t.rs.seed(global_rs.randint_u32_full());
    traders.push_back(std::move(t));
  }
  latency_rs.seed(global_rs.randint_u32_full());
  {
    LatencyDraw draw{P.lat_model, P.lat_mu, P.lat_sigma, P.lat_min, P.lat_max, P.lat_alpha,
                     P.lat_mean, latency_rs};
    if (P.lat_model == LAT_LOGNORMAL || P.lat_model == LAT_UNIFORM || P.lat_model == LAT_PARETO)
      latency_feed.start(draw);
    else
      constant_latency = draw();  // no RNG involved: the same value every time
  }
  (void)global_rs.randint_u32_full();  // random_state_kernel (unused by abides.run)

  // --- Kernel.__init__ / initialize ---
  packed = n_agents <= 0x10000;  // agent ids 0..n_agents-1 fit 16 bits
  // Without negative latencies/delays nothing is ever scheduled before the current time.
  radix = packed && P.lat_min >= 0 && P.lat_max >= 0 && P.default_delay >= 0 &&
          P.pipeline_delay >= 0 && P.computation_delay >= 0;
  current_time = P.start_time;
  // Capacity for 2M order ids up front (only the pages written are touched): growing it by
  // doubling copied it and returned the old block to the OS each time.
  order_pos.reserve(size_t{1} << 21);
  agent_times.assign(n_agents, P.start_time);
  comp_delays.assign(n_agents, P.default_delay);
  last_trade = P.r_bar;  // ExchangeAgent.kernel_initializing: oracle.get_daily_open_price
  set_wakeup(0, P.mkt_close);
  for (int32_t a = 0; a < n_agents; a++) set_wakeup(a, P.start_time);  // Agent.kernel_starting
  current_time = P.start_time;

  // --- Kernel.runner ---
  if (radix) {
    waiting.resize(n_agents);
    waiting_gen.assign(n_agents, 0);
  }
  while (!heap_empty() && current_time != 0 && current_time <= P.stop_time) {
    QEntry e = heap_pop();
    current_time = e.time;
    const int32_t r = e.recipient();
    const bool parked = e.slot == kStandIn;
    if (parked) {
      if (e.info != waiting_gen[r]) continue;  // stale stand-in
      if (agent_times[r] > current_time) {
        if (agent_times[r] > P.stop_time) {
          unpark(r);
        } else {
          e.time = agent_times[r];
          heap_push(e);
        }
        continue;
      }
      std::vector<QEntry>& w = waiting[r];
      std::pop_heap(w.begin(), w.end(), waiting_gt);
      e = w.back();
      w.pop_back();
      e.time = current_time;
    } else if (agent_times[r] > current_time) {  // agent still "in the future": requeue
      if (radix && agent_times[r] <= P.stop_time) {
        defer(e, r);
        continue;
      }
      QEntry re = e;
      re.time = agent_times[r];
      heap_push(re);
      continue;
    }
    agent_times[r] = current_time;
    if (e.slot < 0) {  // wake-up
      has_causal = true;
      causal = e.msg_id;
      deliver_row(e.msg_id, r, r, false, 0, current_time, MT_WAKEUP, false, 0, -1);
      if (r == 0)
        exchange_wakeup(current_time);
      else
        trader_wakeup(trader(r), current_time);
      agent_times[r] += comp_delays[r];
    } else {
      const Message& m = msgs[e.slot];
      agent_times[r] += comp_delays[r];
      has_causal = true;
      causal = m.id;
      if (P.ledger) {
        const SendInfo si = send_info[e.info];
        free_info.push_back(e.info);
        deliver_row(m.id, e.sender(), r, true, si.t_send, si.t_recv, m.type, m.has_order(),
                    m.order.order_id, si.causal);
      } else {
        ++n_messages;
      }
      if (r == 0)
        exchange_receive(current_time, e.sender(), e.slot);
      else
        trader_receive(trader(r), current_time, e.slot);
      release(e.slot);
    }
    if (parked) repark(r);
  }
  return extract();
}

// trace.extract_trace + trace.extract_message_trace
Result Sim::extract() {
  Result res;
  // Trace rows and the ledger rows not handed to the sink (all of them without a sink),
  // both in seq order.
  auto built = out.finish();
  res.trace = std::move(built.first);
  res.messages = std::move(built.second);
  res.n_messages = n_messages;
  return res;
}

}  // namespace

Result run(Params params, MessageSink* sink, TraceSink* trace_sink) {
  Sim sim(std::move(params), sink, trace_sink);
  return sim.run();
}

}  // namespace t3
