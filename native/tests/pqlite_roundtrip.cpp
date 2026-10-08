// Round-trip test for pqlite: writes trace/message files from random columns (extreme int64
// values, wrapping deltas, null patterns, sizes around block boundaries, multi-block
// messages) plus the raw columns as JSON; tools/test_pqlite_roundtrip.py reads both back.
#include <cstdio>
#include <random>
#include <string>
#include "../pqlite.hpp"
#include "../vendor/json.hpp"
using nlohmann::json;
const char* const t3::kMsgTypeNames[t3::MT_COUNT] = {"AGENT_WAKEUP","MarketClosePriceRequestMsg","MarketHoursRequestMsg","MarketHoursMsg","QuerySpreadMsg","QuerySpreadResponseMsg","LimitOrderMsg","CancelOrderMsg","OrderAcceptedMsg","OrderExecutedMsg","OrderCancelledMsg","MarketClosedMsg","MarketClosePriceMsg"};
int main(int argc, char** argv) {
  const size_t n = std::stoul(argv[1]); const unsigned seed = std::stoul(argv[2]); const std::string dir = argv[3];
  std::mt19937_64 R(seed);
  auto pick = [&](int mode, size_t i) -> int64_t {
    switch (mode) {
      case 0: return INT64_MIN + (int64_t)(R() % 3);
      case 1: return INT64_MAX - (int64_t)(R() % 3);
      case 2: return (int64_t)R();
      case 3: return 1612483200000000000LL + (int64_t)i * 37 + (int64_t)(R() % 5);
      default: return (int64_t)(R() % 1000) - 500;
    }
  };
  int mode = (int)(R() % 5);
  t3::TraceColumns t; json jt;
  for (size_t i = 0; i < n; i++) {
    if (R() % 50 == 0) mode = (int)(R() % 5);
    t.t_ns.push_back(pick(mode, i)); t.agent_id.push_back((int32_t)R());
    t.msg_type.push_back((uint8_t)(R() % 6)); t.side.push_back((uint8_t)(R() % 2));
    t.price.push_back(pick((mode + 1) % 5, i)); t.size.push_back(pick(4, i)); t.order_id.push_back(pick((mode + 2) % 5, i));
  }
  jt = {{"t_ns", t.t_ns}, {"agent_id", t.agent_id}, {"msg_type", t.msg_type}, {"side", t.side}, {"price", t.price}, {"size", t.size}, {"order_id", t.order_id}};
  t3::pqlite::write_trace(t, dir + "/trace.parquet");
  // messages in several blocks of random sizes
  t3::pqlite::MessageWriter w(dir + "/message_trace.parquet");
  json jm = {{"t_recv", json::array()}, {"t_send", json::array()}, {"latency", json::array()}, {"src", json::array()}, {"dst", json::array()}, {"message_id", json::array()}, {"msg_type", json::array()}, {"order_id", json::array()}, {"causal", json::array()}};
  size_t done = 0;
  while (done < n) {
    size_t k = std::min<size_t>(n - done, 1 + R() % 70000);
    t3::MessageColumns m;
    for (size_t i = 0; i < k; i++) {
      auto opt = [&](int64_t v, std::vector<int64_t>& vals, std::vector<uint8_t>& nul, const char* key) {
        const int pat = (int)((done + i) % 7);
        const bool isnull = pat == 0 ? (R() % 3 == 0) : (pat == 3 ? true : false);
        vals.push_back(isnull ? 0 : v); nul.push_back(isnull);
        jm[key].push_back(isnull ? json(nullptr) : json(v));
      };
      int64_t tr = pick(mode, done + i); m.t_recv.push_back(tr); jm["t_recv"].push_back(tr);
      opt(pick(3, done + i), m.t_send, m.t_send_null, "t_send");
      int64_t lat = pick(4, i); m.latency.push_back(lat); jm["latency"].push_back(lat);
      int32_t s = (int32_t)R(), d = (int32_t)(R() % 100); m.src.push_back(s); m.dst.push_back(d); jm["src"].push_back(s); jm["dst"].push_back(d);
      int64_t mid = pick(2, i); m.message_id.push_back(mid); jm["message_id"].push_back(mid);
      uint8_t ty = (uint8_t)(R() % t3::MT_COUNT); m.msg_type.push_back(ty); jm["msg_type"].push_back(ty);
      opt(pick(4, i), m.order_id, m.order_id_null, "order_id");
      opt(pick(3, i), m.causal_parent, m.causal_null, "causal");
    }
    w.append(m, done); done += k;
  }
  w.close();
  FILE* f = fopen((dir + "/raw.json").c_str(), "w"); fputs(json({{"trace", jt}, {"msg", jm}}).dump().c_str(), f); fclose(f);
}
