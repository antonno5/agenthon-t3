// Executive summary: run an unchanged mapped public input; optionally measure only the engine.
#include "engine.hpp"
#include <chrono>
#include <fstream>
#include <iostream>
#include <iomanip>
#include <stdexcept>
using namespace t3;
Params read(const char* path) {
  std::ifstream in(path); Params p{}; size_t n;
  in >> p.seed >> p.start_time >> p.mkt_open >> p.mkt_close >> p.stop_time >> p.oracle_close
     >> p.default_delay >> p.r_bar >> p.kappa >> p.fund_vol >> p.megashock_lambda_a
     >> p.megashock_mean >> p.megashock_var >> p.pipeline_delay >> p.computation_delay
     >> p.stp >> p.lat_model >> p.lat_mu >> p.lat_sigma >> p.lat_min >> p.lat_max
     >> p.lat_alpha >> p.lat_mean >> n;
  for (size_t i=0;i<n;++i) { Jump j{}; in >> j.time_ns >> j.magnitude; p.jumps.push_back(j); }
  in >> n;
  for (size_t i=0;i<n;++i) { AgentParams a{}; in >> a.kind >> a.interval >> a.d0 >> a.d1
      >> a.i0 >> a.i1 >> a.i2 >> a.i3; p.agents.push_back(a); }
  if (!in) throw std::runtime_error("invalid config");
  return p;
}
template<class T> void column(std::ofstream& out, const std::vector<T>& v) {
  uint64_t n=v.size(); out.write(reinterpret_cast<char*>(&n), sizeof(n));
  out.write(reinterpret_cast<const char*>(v.data()), v.size()*sizeof(T));
}
int main(int argc, char** argv) {
  if (argc != 3) throw std::runtime_error("driver CONFIG OUTPUT (OUTPUT=- for component)");
  Params p = read(argv[1]); ProtocolCounts c;
  const auto start=std::chrono::steady_clock::now();
#ifdef T3_COMPONENT_DRIVER
  Result r=run_component(std::move(p), &c);
#else
  Result r=run(std::move(p));
#endif
  const auto end=std::chrono::steady_clock::now();
  if (std::string(argv[2]) != "-") {
    std::ofstream out(argv[2], std::ios::binary);
#define COL(group, field) column(out, r.group.field)
    COL(trace,t_ns); COL(trace,agent_id); COL(trace,msg_type); COL(trace,side);
    COL(trace,price); COL(trace,size); COL(trace,order_id);
    COL(messages,t_recv); COL(messages,t_send); COL(messages,latency);
    COL(messages,message_id); COL(messages,order_id); COL(messages,causal_parent);
    COL(messages,t_send_null); COL(messages,order_id_null); COL(messages,causal_null);
    COL(messages,src); COL(messages,dst); COL(messages,msg_type);
#undef COL
    if (!out) throw std::runtime_error("output write failed");
  }
  std::cout << std::setprecision(17) << "{\"messages\":" << r.n_messages << ",\"trace_rows\":" << r.trace.t_ns.size()
    << ",\"engine_seconds\":" << std::chrono::duration<double>(end-start).count()
    << ",\"deliveries\":" << c.deliveries << ",\"fast_events\":" << c.fast_events
    << ",\"inline_deliveries\":" << c.inline_deliveries << ",\"typed_dispatches\":" << c.typed_dispatches
    << ",\"heap_pushes\":" << c.heap_pushes << ",\"heap_pops\":" << c.heap_pops
    << ",\"pool_allocations\":" << c.pool_allocations << ",\"requeues\":" << c.requeues << "}\n";
}
