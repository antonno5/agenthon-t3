// Executive summary: compare the actual original finalizer with streamed output on identical logs.
#include "base_engine.cpp"
#include "trace_stream_visible.hpp"
#include "read_params.hpp"
#include <chrono>
#include <iostream>
#include <random>
#include <cassert>
using namespace t3;
struct Input {
  int64_t t;
  int32_t owner;
  uint8_t type;
  Order order;
};
static Input row(int64_t t, int32_t owner, uint8_t type, int64_t oid,
                 int64_t qty=7, int8_t side=1, int32_t agent=-1, bool fill=true) {
  Order o{}; o.order_id=oid; o.agent_id=agent < 0 ? owner : agent;
  o.side=side; o.quantity=qty; o.limit_price=101; o.has_fill=fill; o.fill_price=102;
  return {t,owner,type,o};
}
static Input quote(int64_t t, uint8_t side, int64_t price, int64_t qty) {
  Input q=row(t,0,TM_QUOTE_UPDATE,-1,qty,side); q.order.limit_price=price; return q;
}
static void populate(Sim& base, const std::vector<Input>& rows, size_t owner_count=32) {
  base.traders.resize(owner_count);
  for (const auto& r: rows) {
    if (r.type==TM_QUOTE_UPDATE) {
      base.quotes.push_back({r.t,static_cast<uint8_t>(r.order.side),r.order.limit_price,r.order.quantity});
    } else {
      const uint8_t ev=r.type==TM_ORDER_SUBMITTED ? EV_SUBMITTED :
        r.type==TM_ORDER_ACCEPTED ? EV_ACCEPTED : r.type==TM_ORDER_CANCELLED ? EV_CANCELLED : EV_EXECUTED;
      base.traders.at(r.owner-1).log.push_back({r.t,ev,r.order});
    }
  }
}
struct Stats { size_t pending_peak=0, dense_slots=0, dense_capacity_bytes=0, row_bytes=0; };
template<bool collect=false>
static TraceColumns candidate(const std::vector<Input>& rows, bool chronological=true, Stats* stats=nullptr) {
  TraceStream stream(chronological);
  for (const auto& r: rows) {
    const auto& o=r.order;
    if (r.type==TM_QUOTE_UPDATE)
      stream.quote(r.t,static_cast<uint8_t>(o.side),o.limit_price,o.quantity);
    else
      stream.order(r.t,r.owner,o.agent_id,r.type,o.side==1 ? SIDE_BID : SIDE_ASK,
                   r.type==TM_PARTIAL_FILL ? (o.has_fill ? o.fill_price : 0) : o.limit_price,
                   o.quantity,o.order_id);
    if constexpr(collect) stats->pending_peak=std::max(stats->pending_peak,stream.pending_.size());
  }
  auto out=stream.finish();
  if constexpr(collect) {
    stats->dense_slots=stream.last_execution_.size();
    stats->dense_capacity_bytes=stream.last_execution_.capacity()*sizeof(size_t);
    stats->row_bytes=sizeof(TraceStream::Row);
  }
  return out;
}
static void equal(const TraceColumns& a, const TraceColumns& b) {
  assert(a.t_ns==b.t_ns && a.agent_id==b.agent_id && a.msg_type==b.msg_type);
  assert(a.side==b.side && a.price==b.price && a.size==b.size && a.order_id==b.order_id);
}
static void check(const std::vector<Input>& rows, bool chronological=true) {
  Sim base(Params{},nullptr); populate(base,rows); equal(base.extract().trace,candidate(rows,chronological));
}
static std::vector<Input> generated(size_t n, uint32_t seed) {
  std::mt19937 rng(seed); std::vector<Input> rows; rows.reserve(n); int64_t t=1;
  for (size_t i=0;i<n;++i) {
    if (rng()%8==0) ++t;
    if (rng()%4==0) rows.push_back(quote(t,rng()%2,100+rng()%30,1+rng()%20));
    else {
      const int64_t oid=rng()%8192;
      rows.push_back(row(t,1+oid%32,rng()%4,oid,1+rng()%100,rng()%2 ? 1 : -1,-1,rng()%2));
    }
  }
  return rows;
}
static uint64_t fingerprint(const TraceColumns& c) {
  uint64_t h=1469598103934665603ULL;
  auto add=[&](const auto& v) {
    const auto* p=reinterpret_cast<const unsigned char*>(v.data());
    for(size_t i=0;i<v.size()*sizeof(v[0]);++i) h=(h^p[i])*1099511628211ULL;
  };
  add(c.t_ns);add(c.agent_id);add(c.msg_type);add(c.side);add(c.price);add(c.size);add(c.order_id);
  return h;
}
int main(int argc, char** argv) {
  if (argc==1) {
    check({});
    auto edges=std::vector<Input>{
      quote(1,SIDE_ASK,110,3),row(1,2,TM_PARTIAL_FILL,8,1),
      quote(1,SIDE_BID,90,4),row(1,1,TM_PARTIAL_FILL,8,2,1,9,false),
      quote(1,SIDE_ASK,111,5),row(1,1,TM_ORDER_ACCEPTED,8),
      row(1,1,TM_PARTIAL_FILL,8,3),quote(1,SIDE_BID,91,6),
      row(2,2,TM_ORDER_CANCELLED,8),quote(2,SIDE_BID,91,6),
      row(3,2,TM_PARTIAL_FILL,8,1),quote(3,SIDE_ASK,112,7),
      row(4,1,TM_ORDER_SUBMITTED,90)};
    check(edges);
    // The last retained execution is FILLED despite cancellation and nonzero remaining qty.
    const auto c=candidate(edges); size_t filled=0;
    for (size_t i=0;i<c.t_ns.size();++i) if(c.msg_type[i]==TM_ORDER_FILLED) {
      ++filled; assert(c.order_id[i]==8 && c.t_ns[i]==3 && c.size[i]==1);
    }
    assert(filled==1 && c.side[0]==SIDE_ASK && c.price[0]==111 && c.side[1]==SIDE_BID);
    assert(c.price[2]==0 && c.agent_id[2]==9); // owner order, missing fill-price
    // An absent bid between two same-time appearances must retain its first position.
    check({quote(1,SIDE_BID,1,1),quote(1,SIDE_ASK,2,2),quote(1,SIDE_ASK,3,3),
           quote(1,SIDE_BID,4,4),quote(2,SIDE_BID,4,4)});
    check({row(4,2,TM_PARTIAL_FILL,2),quote(1,SIDE_ASK,1,1),
           row(2,1,TM_PARTIAL_FILL,2),quote(3,SIDE_ASK,3,3),
           row(4,1,TM_PARTIAL_FILL,2),quote(3,SIDE_ASK,4,4)},false);
    bool rejected=false;
    try { TraceStream s; s.order(2,1,1,0,0,1,1,0); s.order(1,1,1,0,0,1,1,0); }
    catch (const std::runtime_error&) { rejected=true; } assert(rejected);
    rejected=false;
    try { TraceStream s(false); s.quote(2,0,1,1); s.quote(1,0,1,1); }
    catch (const std::runtime_error&) { rejected=true; } assert(rejected);
    std::vector<Input> one_group;
    for(int i=0;i<4096;++i) one_group.push_back(row(0,1+i%32,TM_PARTIAL_FILL,i%17));
    check(one_group);
    check({row(0,1,TM_ORDER_SUBMITTED,0),row(0,1,TM_PARTIAL_FILL,8191),
           row(INT64_MAX,1,TM_PARTIAL_FILL,8191)});
    for (uint32_t seed=0;seed<64;++seed) check(generated(2048,seed));
    std::cout << "{\"executive_summary\":\"Actual base finalizer and candidate agree on edges and 64 generated histories.\",\"accepted\":true,\"generated_histories\":64,\"generated_input_rows\":131072}\n";
    return 0;
  }
  const bool capture_only=std::string(argv[1])=="--capture-check";
  assert(capture_only || std::string(argv[1])=="--bench");
  assert(argc==3);  // only configs from the frozen assigned timing units
  std::vector<Input> rows;
  {
    Sim captured(read_params(argv[2]),nullptr);
    captured.run();  // simulation and input capture are outside component clocks
    for(size_t i=0;i<captured.traders.size();++i) {
      for(const auto& l:captured.traders[i].log) {
        const uint8_t type=l.ev==EV_SUBMITTED ? TM_ORDER_SUBMITTED :
          l.ev==EV_ACCEPTED ? TM_ORDER_ACCEPTED : l.ev==EV_CANCELLED ? TM_ORDER_CANCELLED : TM_PARTIAL_FILL;
        rows.push_back({l.t,static_cast<int32_t>(i+1),type,l.order});
      }
    }
    for(const auto& q:captured.quotes) rows.push_back(quote(q.t,q.side,q.price,q.qty));
  }
  // Recover chronological input from real retained logs. Stable ties preserve each
  // owner's sequence and quote appearance order. Sorting this immutable replay input
  // is outside both sides' component clocks.
  std::stable_sort(rows.begin(),rows.end(),[](const Input& a,const Input& b){return a.t<b.t;});
  size_t owner_count=0; for(const auto& r:rows) owner_count=std::max(owner_count,static_cast<size_t>(r.owner));
  Sim base(Params{},nullptr); populate(base,rows,owner_count);
  Stats stats; const auto a=base.extract().trace, b=candidate<true>(rows,true,&stats); equal(a,b);
  size_t max_group=0,group=0,orders=0,quotes=0; int64_t t=-1;
  for(const auto& r:rows) {
    if(r.t!=t) {max_group=std::max(max_group,group);group=0;t=r.t;} ++group;
    if(r.type==TM_QUOTE_UPDATE) ++quotes; else ++orders;
  }
  max_group=std::max(max_group,group);
  if(capture_only) {
    std::cout << "{\"executive_summary\":\"Untimed replay of real captured base logs agrees with candidate output.\",\"accepted\":true,\"input_rows\":" << rows.size()
      << ",\"output_rows\":" << a.t_ns.size() << ",\"pending_peak_rows\":" << stats.pending_peak
      << ",\"dense_execution_slots\":" << stats.dense_slots << "}\n";
    return 0;
  }
  struct Timing {double total, finish;};
  auto measure=[&](bool cand) {
    TraceColumns c; double finish=0;
    Sim captured(Params{},nullptr); captured.traders.resize(owner_count);
    const auto start=std::chrono::steady_clock::now();
    if(cand) {
      // Time all online capture and flush work. No per-row diagnostic counters.
      c=candidate(rows);
    } else {
      populate(captured,rows,owner_count);
      const auto finish_start=std::chrono::steady_clock::now();
      c=captured.extract().trace;
      finish=std::chrono::duration<double>(std::chrono::steady_clock::now()-finish_start).count();
    }
    const auto stop=std::chrono::steady_clock::now(); equal(a,c);
    return Timing{std::chrono::duration<double>(stop-start).count(),finish};
  };
  // Exactly one excluded warmup per side, then fixed AB/BA/AB/BA/AB pairs.
  const auto wa=measure(false), wb=measure(true);
  std::cout << "{\"executive_summary\":\"Actual original log capture plus extract versus all streamed capture and finalization on identical captured logs from an assigned timing unit; excluded from full-run medians.\",\"input_rows\":" << rows.size()
    << ",\"order_snapshot_rows_baseline\":" << orders << ",\"order_snapshot_rows_candidate\":0,\"quote_log_rows_baseline\":" << quotes
    << ",\"pending_peak_rows_candidate\":" << stats.pending_peak << ",\"pending_row_bytes_candidate\":" << stats.row_bytes
    << ",\"dense_execution_slots_candidate\":" << stats.dense_slots << ",\"dense_execution_capacity_bytes_candidate\":" << stats.dense_capacity_bytes
    << ",\"raw_max_timestamp_group_rows\":" << max_group << ",\"output_rows\":" << a.t_ns.size()
    << ",\"output_fingerprint\":" << fingerprint(a) << ",\"baseline_order_log_bytes\":" << orders*sizeof(OrderLog)
    << ",\"baseline_quote_log_bytes\":" << quotes*sizeof(QuoteLog) << ",\"warmup_seconds\":[" << wa.total << ',' << wb.total << "],\"pairs\":[";
  for(int i=0;i<5;++i) {
    Timing ta,tb; if(i%2==0){ta=measure(false);tb=measure(true);}else{tb=measure(true);ta=measure(false);}
    if(i) std::cout << ',';
    std::cout << "{\"index\":" << i << ",\"order\":\"" << (i%2==0?"AB":"BA") << "\",\"baseline_seconds\":" << ta.total << ",\"candidate_seconds\":" << tb.total
              << ",\"baseline_extract_only_seconds\":" << ta.finish << '}';
  }
  std::cout << "]}\n";
}
