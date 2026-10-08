// Executive summary: read the same mapper-built parameters for standalone engines and capture diagnostics.
#pragma once
#include "engine.hpp"
#include <fstream>
#include <stdexcept>
inline t3::Params read_params(const char* path) {
  using namespace t3;
  std::ifstream in(path); Params p{}; size_t n;
  in >> p.seed >> p.start_time >> p.mkt_open >> p.mkt_close >> p.stop_time >> p.oracle_close
     >> p.default_delay >> p.r_bar >> p.kappa >> p.fund_vol >> p.megashock_lambda_a
     >> p.megashock_mean >> p.megashock_var >> p.pipeline_delay >> p.computation_delay
     >> p.stp >> p.lat_model >> p.lat_mu >> p.lat_sigma >> p.lat_min >> p.lat_max
     >> p.lat_alpha >> p.lat_mean >> n;
  for(size_t i=0;i<n;++i) {Jump j{}; in>>j.time_ns>>j.magnitude;p.jumps.push_back(j);}
  in>>n;
  for(size_t i=0;i<n;++i) {
    AgentParams a{};in>>a.kind>>a.interval>>a.d0>>a.d1>>a.i0>>a.i1>>a.i2>>a.i3;p.agents.push_back(a);
  }
  if(!in) throw std::runtime_error("invalid params");
  return p;
}
