// Native re-implementation of the exact ABIDES code path the Track-3 adapter exercises:
// abides_core.Kernel (runner / send_message / set_wakeup / message ledger), ExchangeAgent +
// OrderBook + PriceLevel (limit orders, cancels, opt-in STP), TradingAgent bookkeeping, the
// adapter's four ScheduledAgent subclasses, SparseMeanRevertingOracle, ScenarioLatencyModel,
// and trace.py's extraction. Every RNG draw, message id, order id, tie-break and float
// operation is taken in the same order as the Python reference, so the emitted trace and
// message ledger are byte-identical. Scenarios outside the validated envelope never reach
// this code: abides_fork/native.py routes them to the Python ABIDES path instead.
#pragma once

#include <cstdint>
#include <map>
#include <string>
#include <vector>

#include "rng.hpp"

namespace t3 {

// ---- scenario parameters (built by abides_fork/native.py with the adapter's own rules) ----
enum AgentKind : int { NOISE = 0, MARKET_MAKER = 1, VALUE = 2, MOMENTUM = 3 };
enum LatencyKind : int { LAT_LOGNORMAL = 0, LAT_UNIFORM = 1, LAT_PARETO = 2, LAT_CONSTANT = 3 };
enum StpPolicy : int { STP_NONE = 0, STP_CANCEL_OLDEST = 1, STP_OTHER = 2 };

struct AgentParams {
  int kind;
  int64_t interval;  // already int(max(1, interval_ns))
  // NOISE: d0 = order_size_mean, d1 = order_size_std, i0 = price_offset_ticks, i1 = reference_price
  // MARKET_MAKER: i0 = spread_ticks, i1 = depth_levels, i2 = size_per_level, i3 = reference_price
  // VALUE: d0 = sigma_n, i0 = size, i1 = threshold_ticks
  // MOMENTUM: i0 = size, i1 = threshold_ticks, i2 = lookback
  double d0 = 0, d1 = 0;
  int64_t i0 = 0, i1 = 0, i2 = 0, i3 = 0;
};

struct Jump {
  int64_t time_ns;
  int64_t magnitude;
  bool consumed = false;
};

struct Params {
  uint32_t seed;
  int64_t start_time, mkt_open, mkt_close, stop_time;
  int64_t oracle_close;  // the oracle's own mkt_close (16:00), not the exchange's
  int64_t default_delay;
  // oracle
  int64_t r_bar;
  double kappa, fund_vol, megashock_lambda_a, megashock_mean, megashock_var;
  std::vector<Jump> jumps;
  // exchange
  int64_t pipeline_delay, computation_delay;
  int stp;
  // latency
  int lat_model;
  double lat_mu, lat_sigma, lat_min, lat_max, lat_alpha, lat_mean;
  std::vector<AgentParams> agents;
};

// ---- outputs (column-major, ready for the parquet writer) ----
enum TraceMsgType : uint8_t {
  TM_ORDER_SUBMITTED = 0,
  TM_ORDER_ACCEPTED = 1,
  TM_ORDER_CANCELLED = 2,
  TM_PARTIAL_FILL = 3,
  TM_ORDER_FILLED = 4,
  TM_QUOTE_UPDATE = 5,
};
enum TraceSide : uint8_t { SIDE_BID = 0, SIDE_ASK = 1 };

struct TraceColumns {
  std::vector<int64_t> t_ns;
  std::vector<int32_t> agent_id;
  std::vector<uint8_t> msg_type;
  std::vector<uint8_t> side;
  std::vector<int64_t> price, size, order_id;
};

// Ledger msg_type codes; names in kMsgTypeNames (engine.cpp).
enum MsgType : uint8_t {
  MT_WAKEUP = 0,  // ledger name "AGENT_WAKEUP"
  MT_MKT_CLOSE_PRICE_REQ,
  MT_MKT_HOURS_REQ,
  MT_MKT_HOURS,
  MT_QUERY_SPREAD,
  MT_QUERY_SPREAD_RESP,
  MT_LIMIT_ORDER,
  MT_CANCEL_ORDER,
  MT_ORDER_ACCEPTED,
  MT_ORDER_EXECUTED,
  MT_ORDER_CANCELLED,
  MT_MKT_CLOSED,
  MT_MKT_CLOSE_PRICE,
  MT_COUNT
};
extern const char* const kMsgTypeNames[MT_COUNT];

struct MessageColumns {
  std::vector<int64_t> t_recv, t_send, latency, message_id, order_id, causal_parent;
  std::vector<uint8_t> t_send_null, order_id_null, causal_null;
  std::vector<int32_t> src, dst;
  std::vector<uint8_t> msg_type;
};

struct Result {
  TraceColumns trace;
  MessageColumns messages;
};

// Throws std::runtime_error on any state the Python reference would have raised on.
Result run(Params params);

}  // namespace t3
