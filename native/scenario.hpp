// Native translation of native.py::_build and scenario_params.py. Unusual JSON
// types are delegated before simulation instead of approximating Python coercion.
#pragma once
#include "engine.hpp"
#include "nplog.hpp"
#include "vendor/json.hpp"
#include <cmath>
#include <limits>
#include <stdexcept>
#include <algorithm>

namespace t3cli {
using Json = nlohmann::ordered_json;
struct Unsupported : std::runtime_error { using std::runtime_error::runtime_error; };
inline void require(bool ok) { if (!ok) throw Unsupported("scenario outside native envelope"); }
inline double number(const Json& j) {
  // Python accepts further coercions; preserve those through the unchanged adapter.
  require(j.is_number() || j.is_boolean());
  double v = j.is_boolean() ? (j.get<bool>() ? 1.0 : 0.0) : j.get<double>();
  require(std::isfinite(v)); return v;
}
inline int64_t integer(const Json& j) {
  if (j.is_number_unsigned()) { auto v = j.get<uint64_t>(); require(v <= INT64_MAX); return v; }
  if (j.is_number_integer()) return j.get<int64_t>();
  double v = number(j);
  require(v >= -0x1p63 && v < 0x1p63); return static_cast<int64_t>(v);
}
inline double fget(const Json& j, const char* k, double d) { return number(j.value(k, Json(d))); }
inline int64_t iget(const Json& j, const char* k, int64_t d) { return integer(j.value(k, Json(d))); }
inline bool truth(const Json& j) {
  if (j.is_null()) return false;
  if (j.is_boolean()) return j.get<bool>();
  if (j.is_number()) return number(j) != 0;
  if (j.is_string()) return !j.get_ref<const std::string&>().empty();
  return !j.empty();
}
inline int64_t clamp_int(const Json& j, int64_t lo) {
  // max precedes int in the Python constructors; preserve truncation after clamping.
  if (j.is_number_integer() || j.is_boolean()) return std::max(lo, integer(j));
  return integer(std::max(static_cast<double>(lo), number(j)));
}
inline int64_t interval(const Json& j) {
  if (j.contains("rebalance_interval_ns")) return iget(j, "rebalance_interval_ns", 0);
  double hz = fget(j, "arrival_rate_hz", 1.0);
  return integer(hz > 0 ? 1e9 / hz : 1e9);
}
inline t3::Params build(const Json& s) {
  t3::Params p{};
  const auto& seed = s.at("seed");
  require(seed.is_number_integer()); auto sv = integer(seed);
  require(sv >= 0 && sv <= 0xffffffffLL); p.seed = sv;
  const auto& ex = s.at("exchange_config"); require(ex.is_object());
  bool proto = truth(ex.value("protocol_enforcement", Json(false)));
  p.pipeline_delay = proto ? iget(ex, "ack_delay_ns", 0) : 0;
  p.computation_delay = proto ? iget(ex, "compute_delay_ns", 0) : 0;
  require(p.pipeline_delay >= 0 && p.pipeline_delay <= 1000000000000000LL &&
          p.computation_delay >= 0 && p.computation_delay <= 1000000000000000LL);
  auto stp = ex.value("stp_policy", Json());
  p.stp = 0;
  if (proto && truth(stp)) { require(stp.is_string()); p.stp = stp == "cancel_oldest" ? 1 : 2; }
  const auto& oc = s.at("oracle_config"); require(oc.is_object());
  auto op = oc.value("params", Json::object()); require(op.is_object());
  p.r_bar = iget(op, "initial_price", 100000);
  auto horizon = integer(s.at("horizon_ns"));
  require(p.r_bar >= 0 && p.r_bar <= 1000000000000LL && horizon >= 1 && horizon <= 1000000000000000LL);
  p.start_time = 1612483200000000000LL;
  p.mkt_open = p.start_time + 34200000000000LL;
  p.mkt_close = p.mkt_open + horizon;
  p.stop_time = p.mkt_close + 1000000000LL;
  p.oracle_close = p.start_time + 57600000000000LL;
  p.default_delay = 50;
  double k = fget(op, "kappa", 0), rate = fget(op, "jump_intensity", 0);
  p.kappa = k > 0 ? k / 1e9 : 1.67e-16;
  p.megashock_lambda_a = rate > 0 ? rate / 1e9 : 2.77778e-18;
  p.fund_vol = fget(op, "sigma", 5e-5);
  p.megashock_mean = fget(op, "jump_sigma", 0);
  if (p.megashock_mean == 0) p.megashock_mean = 1000;
  p.megashock_var = 50000;
  require(p.kappa > 0 && p.megashock_lambda_a > 0);
  auto sj = op.value("scheduled_jump", Json());
  if (truth(sj)) {
    require(sj.is_object()); auto delta = integer(sj.at("time_ns")), mag = integer(sj.at("magnitude"));
    // Check before addition so unsupported input cannot invoke signed overflow.
    require(delta > -(1LL << 62) - p.mkt_open && delta < (1LL << 62) - p.mkt_open);
    require(mag >= -(1LL << 40) && mag <= (1LL << 40));
    p.jumps.push_back({p.mkt_open + delta, mag, false});
  }
  require(s.contains("latency_config") && truth(s.at("latency_config")));
  const auto& lc = s.at("latency_config"); require(lc.is_object());
  auto lp = lc.value("params", Json::object()); require(lp.is_object());
  auto model = lc.value("model", Json("deterministic")); require(model.is_string());
  p.lat_model = model == "log_normal" ? 0 : model == "uniform" ? 1 : model == "pareto" ? 2 : 3;
  p.lat_mean = fget(lp, "mean_ns", 0); p.lat_sigma = fget(lp, "sigma", 0);
  p.lat_min = fget(lp, "min_ns", 0); p.lat_max = fget(lp, "max_ns", 1e12);
  p.lat_alpha = fget(lp, "alpha", 1.5);
  require(p.lat_model != 0 || p.lat_sigma >= 0);
  require(p.lat_model != 2 || p.lat_alpha > 0);
  require(std::abs(p.lat_mean) <= 1e15 && std::abs(p.lat_min) <= 1e15 && std::abs(p.lat_max) <= 1e15);
  if (p.lat_mean > 0) require(t3::numpy_log(p.lat_mean, &p.lat_mu));
  require(s.at("agent_configs").is_array());
  for (const auto& ac : s.at("agent_configs")) {
    auto type = ac.at("agent_type"); require(type.is_string());
    auto a = ac.value("params", Json::object()); require(a.is_object());
    t3::AgentParams ap{}; ap.interval = std::max(int64_t(1), interval(a));
    require(ap.interval <= 1000000000000000LL);
    if (type == "NoiseTrader") {
      ap.kind = 0; ap.d0 = fget(a, "order_size_mean", 10); ap.d1 = fget(a, "order_size_std", 2);
      ap.i0 = iget(a, "price_offset_ticks", 5); ap.i1 = p.r_bar;
      require(ap.d1 >= 0 && ap.i0 >= 0 && ap.i0 <= 1000000000 && std::abs(ap.d0) <= 1e12 && ap.d1 <= 1e12);
    } else if (type == "MarketMaker") {
      ap.kind = 1; ap.i0 = clamp_int(a.value("spread_ticks", Json(2)), 2);
      ap.i1 = clamp_int(a.value("depth_levels", Json(3)), 1);
      ap.i2 = clamp_int(a.value("size_per_level", Json(10)), 1); ap.i3 = p.r_bar;
      require(ap.i0 <= 1000000000 && ap.i1 <= 10000 && ap.i2 <= 1000000000000LL);
    } else if (type == "ValueTrader" || type == "MomentumTrader") {
      ap.kind = type == "ValueTrader" ? 2 : 3;
      double size = fget(a, "order_size_mean", ap.kind == 2 ? 25 : 15);
      ap.i1 = iget(a, "threshold_ticks", 2);
      require(std::abs(size) <= 1e12 && ap.i1 >= -(1LL << 40) && ap.i1 <= (1LL << 40));
      ap.i0 = std::max(int64_t(1), integer(std::nearbyint(size)));
      if (ap.kind == 2) ap.d0 = 1000;
      else { ap.i2 = clamp_int(a.value("lookback", Json(5)), 1); require(ap.i2 <= 1000000); }
    } else throw Unsupported("unknown agent type");
    auto count = std::max(int64_t(0), integer(ac.at("count")));
    require(count <= 200000 && p.agents.size() + count <= 200000);
    p.agents.insert(p.agents.end(), static_cast<size_t>(count), ap);
  }
  return p;
}

// Diagnostic endpoint used for differential tests; mirrors every native.py field.
inline Json describe(const t3::Params& p) {
  Json j = {{"seed", p.seed}, {"start_time", p.start_time}, {"mkt_open", p.mkt_open},
    {"mkt_close", p.mkt_close}, {"stop_time", p.stop_time}, {"oracle_close", p.oracle_close},
    {"default_delay", p.default_delay}, {"r_bar", p.r_bar}, {"kappa", p.kappa},
    {"fund_vol", p.fund_vol}, {"megashock_lambda_a", p.megashock_lambda_a},
    {"megashock_mean", p.megashock_mean}, {"megashock_var", p.megashock_var},
    {"jumps", Json::array()}, {"pipeline_delay", p.pipeline_delay},
    {"computation_delay", p.computation_delay}, {"stp", p.stp}, {"lat_model", p.lat_model},
    {"lat_mu", p.lat_mu}, {"lat_sigma", p.lat_sigma}, {"lat_min", p.lat_min},
    {"lat_max", p.lat_max}, {"lat_alpha", p.lat_alpha}, {"lat_mean", p.lat_mean},
    {"agents", Json::array()}};
  for (const auto& x : p.jumps) j["jumps"].push_back({x.time_ns, x.magnitude});
  for (const auto& a : p.agents) j["agents"].push_back({a.kind, a.interval, a.d0, a.d1, a.i0, a.i1, a.i2, a.i3});
  return j;
}
}  // namespace t3cli
