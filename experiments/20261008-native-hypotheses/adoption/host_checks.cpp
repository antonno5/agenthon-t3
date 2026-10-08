// Executive summary: compare grouped extraction and complete native simulations
// with the unchanged implementation on the same host; this is not Docker timing.
#include "engine.hpp"
#include "book.hpp"
#include "agent_orders.hpp"
#include <algorithm>
#include <cmath>
#include <deque>
#include <limits>
#include <stdexcept>
#include <unordered_map>
#include <iostream>
#include <random>
#include <tuple>
#define t3 t3_baseline
#include "baseline/engine.hpp"
#undef t3
// Test-only access to the real extraction code. Standard headers are already loaded.
#define private public
#include "engine.cpp"
#undef private

void check(bool value) { if (!value) throw std::runtime_error("differential mismatch"); }

template<class A, class B> void compare(const A& a, const B& b) {
  check(a.trace.t_ns == b.trace.t_ns); check(a.trace.agent_id == b.trace.agent_id);
  check(a.trace.msg_type == b.trace.msg_type); check(a.trace.side == b.trace.side);
  check(a.trace.price == b.trace.price); check(a.trace.size == b.trace.size);
  check(a.trace.order_id == b.trace.order_id);
#define COLUMN(c) check(a.messages.c == b.messages.c)
  COLUMN(t_recv); COLUMN(t_send); COLUMN(latency); COLUMN(message_id); COLUMN(order_id);
  COLUMN(causal_parent); COLUMN(t_send_null); COLUMN(order_id_null); COLUMN(causal_null);
  COLUMN(src); COLUMN(dst); COLUMN(msg_type);
#undef COLUMN
}

std::vector<t3::Row> legacy_rows(std::vector<t3::Row> rows) {
  // Recreate the former input: each agent's log, in append order. Then use the
  // former global stable comparator, independently of the candidate tie keys.
  std::sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) {
    return std::tie(a.log_owner, a.log_sequence) < std::tie(b.log_owner, b.log_sequence);
  });
  std::stable_sort(rows.begin(), rows.end(), [](const auto& a, const auto& b) {
    return std::tie(a.t, a.oid) < std::tie(b.t, b.oid);
  });
  std::map<int64_t, size_t> last;
  for (size_t i = 0; i < rows.size(); ++i)
    if (rows[i].type == t3::TM_PARTIAL_FILL) last[rows[i].oid] = i;
  for (const auto& kv : last) rows[kv.second].type = t3::TM_ORDER_FILLED;
  return rows;
}

t3::Result extracted(std::vector<t3::Row> rows, std::vector<t3::QuoteLog> quotes = {}) {
  t3::Sim sim(t3::Params{});
  sim.order_rows = std::move(rows); sim.quotes = std::move(quotes);
  return sim.extract();
}

void compare_rows(const std::vector<t3::Row>& rows) {
  const auto ref = legacy_rows(rows);
  const auto got = extracted(rows).trace;
  check(got.t_ns.size() == ref.size());
  for (size_t i = 0; i < ref.size(); ++i) {
    check(got.t_ns[i] == ref[i].t); check(got.agent_id[i] == ref[i].agent);
    check(got.msg_type[i] == ref[i].type); check(got.side[i] == ref[i].side);
    check(got.price[i] == ref[i].price); check(got.size[i] == ref[i].size);
    check(got.order_id[i] == ref[i].oid);
  }
}

template<class P> P params(uint32_t seed, int latency, int stp) {
  P p{};
  p.seed = seed; p.start_time = 1000000; p.mkt_open = 1001000;
  p.mkt_close = 1020000; p.stop_time = 1021000; p.oracle_close = 1100000;
  p.default_delay = 50; p.r_bar = 10000; p.kappa = 1e-7; p.fund_vol = 0.001;
  p.megashock_lambda_a = 1e-8; p.megashock_mean = 100; p.megashock_var = 100;
  p.pipeline_delay = 0; p.computation_delay = 0; p.stp = stp;
  p.lat_model = latency; p.lat_mu = 2; p.lat_sigma = 0.7;
  p.lat_min = 0; p.lat_max = latency == 3 ? 0 : 100; p.lat_alpha = 1.5; p.lat_mean = 0;
  p.agents.resize(5);
  p.agents[0].kind = 1; p.agents[0].interval = 250;
  p.agents[0].i0 = 2; p.agents[0].i1 = 6; p.agents[0].i2 = 5; p.agents[0].i3 = p.r_bar;
  for (int i : {1, 2}) {
    p.agents[i].kind = 0; p.agents[i].interval = 100;
    p.agents[i].d0 = 7; p.agents[i].d1 = 2; p.agents[i].i0 = 4; p.agents[i].i1 = p.r_bar;
  }
  p.agents[3].kind = 2; p.agents[3].interval = 150;
  p.agents[3].d0 = 1000; p.agents[3].i0 = 3; p.agents[3].i1 = -1;
  p.agents[4].kind = 3; p.agents[4].interval = 200;
  p.agents[4].i0 = 4; p.agents[4].i1 = 0; p.agents[4].i2 = 2;
  return p;
}


void compare_quote_merge(const std::vector<t3::Row>& rows,
                         const std::vector<t3::QuoteLog>& quotes) {
  using namespace t3;
  std::vector<Row> ref;
  std::map<std::pair<int64_t, uint8_t>, size_t> positions;
  for (const auto& q : quotes) {
    const auto key = std::make_pair(q.t, q.side);
    const Row row{q.t,0,TM_QUOTE_UPDATE,q.side,q.price,q.qty,-1};
    const auto it = positions.find(key);
    if (it == positions.end()) {
      positions.emplace(key, ref.size()); ref.push_back(row);
    } else ref[it->second] = row;
  }
  const auto orders = legacy_rows(rows);
  ref.insert(ref.end(), orders.begin(), orders.end());
  std::stable_sort(ref.begin(), ref.end(), [](const auto& a, const auto& b) {
    return std::tie(a.t, a.oid) < std::tie(b.t, b.oid);
  });
  const auto got = extracted(rows, quotes).trace;
  check(got.t_ns.size() == ref.size());
  for (size_t i = 0; i < ref.size(); ++i) {
    check(got.t_ns[i] == ref[i].t); check(got.agent_id[i] == ref[i].agent);
    check(got.msg_type[i] == ref[i].type); check(got.side[i] == ref[i].side);
    check(got.price[i] == ref[i].price); check(got.size[i] == ref[i].size);
    check(got.order_id[i] == ref[i].oid);
  }
}

void combined_quote_checks() {
  using namespace t3;
  compare_quote_merge({}, {});
  // A side's absence produces no row: disappearance/reappearance keeps its
  // first position and last observed value, including ties with executions.
  const std::vector<Row> rows = {
    {10,2,TM_PARTIAL_FILL,SIDE_BID,102,2,1,2,0},
    {10,1,TM_PARTIAL_FILL,SIDE_BID,101,3,1,1,1},
    {11,2,TM_ORDER_CANCELLED,SIDE_BID,100,4,1,2,2},
  };
  const std::vector<QuoteLog> quotes = {
    {9,SIDE_ASK,110,1},{9,SIDE_ASK,111,2},
    {10,SIDE_ASK,112,3},{10,SIDE_BID,99,4},
    {10,SIDE_ASK,113,5},{10,SIDE_BID,100,6},
    {10,SIDE_ASK,114,7},{11,SIDE_BID,101,8},
  };
  compare_quote_merge(rows, quotes);
  compare_quote_merge({}, quotes);
  compare_quote_merge(rows, {});
  std::mt19937 rng(120261008);
  for (int trial = 0; trial < 128; ++trial) {
    std::vector<Row> events;
    std::vector<QuoteLog> updates;
    int64_t t = 0;
    for (int i = 0; i < 1024; ++i) {
      t += rng()%3;
      const int32_t owner = 1 + rng()%4;
      events.push_back(Row{t,owner,static_cast<uint8_t>(rng()%4),
          static_cast<uint8_t>(rng()%2),static_cast<int64_t>(rng()%100),
          static_cast<int64_t>(rng()%10),static_cast<int64_t>(rng()%32),
          owner,static_cast<uint64_t>(i)});
    }
    t = 0;
    for (int i = 0; i < 4096; ++i) {
      t += rng()%2;
      updates.push_back(QuoteLog{t,static_cast<uint8_t>(rng()%2),
                                 static_cast<int64_t>(rng()%100),
                                 static_cast<int64_t>(rng()%20)});
    }
    compare_quote_merge(events, updates);
  }
  std::vector<Row> events;
  std::vector<QuoteLog> updates;
  for (int64_t i = 0; i < 20000; ++i)
    events.push_back(Row{i/4,1,TM_PARTIAL_FILL,SIDE_BID,100,1,i%100,1,static_cast<uint64_t>(i)});
  for (int64_t i = 0; i < 100000; ++i)
    updates.push_back(QuoteLog{i/12,static_cast<uint8_t>(i%2),100+i%3,1+i%7});
  compare_quote_merge(events, updates);
  std::cout << "PASS: direct quote merge, timestamp ties, absent sides, 128 randomized "
               "combined histories and a 100000-quote/20000-order case\n";
}

int main() {
  combined_quote_checks();
  using namespace t3;
  compare_rows({});
  // Same id and timestamp: kernel visits agent 2 first, former extraction agent 1 first.
  // The final execution at t=11 must stay FILLED even though cancellation follows it.
  const std::vector<Row> focus = {
    {10,2,TM_ORDER_SUBMITTED,SIDE_BID,100,9,7,2,0},
    {10,1,TM_ORDER_SUBMITTED,SIDE_BID,100,9,7,1,1},
    {10,1,TM_ORDER_ACCEPTED,SIDE_BID,100,9,7,1,2},
    {10,2,TM_PARTIAL_FILL,SIDE_BID,101,2,7,2,3},
    {10,1,TM_PARTIAL_FILL,SIDE_BID,102,3,7,1,4},
    {10,1,TM_ORDER_CANCELLED,SIDE_BID,100,6,7,1,5},
    {11,2,TM_PARTIAL_FILL,SIDE_BID,103,1,7,2,6},
    {11,2,TM_ORDER_CANCELLED,SIDE_BID,100,6,7,2,7},
    {11,1,TM_ORDER_ACCEPTED,SIDE_ASK,110,5,8,1,8},
  };
  compare_rows(focus);
  auto got = extracted(focus).trace;
  check(got.price[2] == 102 && got.msg_type[2] == TM_PARTIAL_FILL);
  check(got.price[5] == 101 && got.msg_type[5] == TM_PARTIAL_FILL);
  check(got.price[6] == 103 && got.msg_type[6] == TM_ORDER_FILLED);
  // Missing fill price stays zero; owner provenance differs from emitted agent id.
  Sim append_sim(Params{}); Trader a; a.id = 2; a.current_time = 10;
  Order order{4,1,1,100,3};
  append_sim.append_order_row(a, EV_SUBMITTED, order);
  append_sim.append_order_row(a, EV_ACCEPTED, order);
  append_sim.append_order_row(a, EV_EXECUTED, order);
  append_sim.append_order_row(a, EV_CANCELLED, order);
  got = append_sim.extract().trace;
  check(got.price == std::vector<int64_t>({100,100,0,100}));
  check(got.msg_type == std::vector<uint8_t>({TM_ORDER_SUBMITTED,TM_ORDER_ACCEPTED,TM_ORDER_FILLED,TM_ORDER_CANCELLED}));
  // Quote dedup uses last row per side, first-appearance side order, before lifecycle ties.
  got = extracted(focus, {{10,SIDE_ASK,110,8},{10,SIDE_BID,99,9},
                          {10,SIDE_ASK,111,7},{11,SIDE_BID,100,6}}).trace;
  check(got.t_ns.size() == focus.size() + 3);
  check(got.price[0] == 111 && got.side[0] == SIDE_ASK && got.order_id[0] == -1);
  check(got.price[1] == 99 && got.side[1] == SIDE_BID && got.order_id[1] == -1);
  check(got.price[8] == 100 && got.msg_type[8] == TM_QUOTE_UPDATE);
  std::mt19937 rng(20261008);
  for (int trial = 0; trial < 256; ++trial) {
    std::vector<Row> rows;
    int64_t t = 1;
    for (int i = 0; i < 2000; ++i) {
      t += rng() % 3;
      const int32_t owner = 1 + rng() % 4;
      rows.push_back(Row{t,owner,static_cast<uint8_t>(rng()%4),static_cast<uint8_t>(rng()%2),
                         static_cast<int64_t>(rng()%100),static_cast<int64_t>(rng()%10),
                         static_cast<int64_t>(rng()%32),owner,static_cast<uint64_t>(i)});
    }
    compare_rows(rows);
    // Exercise timestamp regrouping, retaining original per-agent append provenance.
    for (auto& row : rows) row.t = rng() % 50;
    compare_rows(rows);
  }
  size_t simulations = 0, executions = 0, partials = 0, cancellations = 0;
  for (uint32_t seed = 1; seed <= 12; ++seed)
    for (int latency : {0,1,2,3}) for (int stp : {0,1,2}) {
      const auto actual = t3::run(params<t3::Params>(seed,latency,stp));
      const auto baseline = t3_baseline::run(params<t3_baseline::Params>(seed,latency,stp));
      compare(actual,baseline); ++simulations;
      for (auto type : actual.trace.msg_type) {
        executions += type == TM_ORDER_FILLED; partials += type == TM_PARTIAL_FILL;
        cancellations += type == TM_ORDER_CANCELLED;
      }
    }
  check(executions > 0 && partials > 0 && cancellations > 0);
  std::cout << "PASS: focused lifecycle/tie/quote cases, 512 histories (1,024,000 rows), "
            << simulations << " full engine differential simulations; filled=" << executions
            << " partial=" << partials << " cancelled=" << cancellations << '\n';
}
