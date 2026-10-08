// Executive summary: exercise exact ordering, inline lifetimes and shared references without a scenario.
#define T3_PROTOCOL_TESTS
#include "engine.cpp"
#include <iostream>
#include <random>
#include <tuple>
namespace t3 { namespace {
struct ProtocolProbe {
  static void check(bool b) { if(!b) throw std::runtime_error("protocol invariant failed"); }
  static QEntry event(int64_t t,int s,int r,int64_t id,int slot) { return {t,s,r,id,slot,10,20,7}; }
  static void test() {
    Sim sim(Params{},nullptr,nullptr,true);
    // Exhaust all positions of the candidate in equal-time sender/recipient/id competition.
    for(int axis=0;axis<4;++axis) for(int delta=-1;delta<=1;++delta) {
      sim.have_pending=false; sim.heap.clear();
      int slot=sim.new_msg(MT_ORDER_ACCEPTED); sim.msgs[slot].refs=1;
      sim.msgs[slot].order.order_id=99;
      QEntry e=event(100,2,3,4,slot), h=e;
      if(axis==0) h.time+=delta;
      if(axis==1) h.sender+=delta;
      if(axis==2) h.recipient+=delta;
      if(axis==3) h.msg_id+=delta;
      h.slot=123; sim.enqueue(e); sim.heap_push(h);
      QEntry first=sim.next_event();
      check((first.slot==kIncoming)==(h>e));
      if(first.slot==kIncoming) check(sim.msgs[first.slot].order.order_id==99);
    }
    sim.have_pending=false; sim.heap.clear(); sim.free_slots.clear(); sim.msgs.pooled.clear();
    // Pending owns a snapshot; new outgoing messages cannot mutate it.
    int slot=sim.new_msg(MT_QUERY_SPREAD_RESP); sim.msgs[slot].refs=1;
    sim.msgs[slot].has_bid=true; sim.msgs[slot].bid_p=43;
    sim.enqueue(event(30,0,1,sim.msgs[slot].id,slot));
    slot=sim.new_msg(MT_ORDER_ACCEPTED); sim.msgs[slot].refs=1;
    sim.enqueue(event(40,0,1,sim.msgs[slot].id,slot));
    QEntry first=sim.next_event(); const Message& active=sim.msgs[first.slot];
    check(active.has_bid && active.bid_p==43);
    sim.new_msg(MT_CANCEL_ORDER); check(active.has_bid && active.bid_p==43);
    // Delayed inline delivery materializes once and preserves send-time ledger fields.
    QEntry delayed=first; delayed.time=80; sim.materialize(delayed,active);
    auto ack=sim.next_event(); sim.release(ack.slot);
    auto re=sim.next_event(); check(re.time==80 && re.t_send==10 && re.t_recv==20 && re.causal==7);
    check(sim.msgs[re.slot].bid_p==43); sim.release(re.slot);
    // A shared broadcast must not free its slot after only its first recipient.
    int shared=sim.new_shared_msg(MT_MKT_CLOSE_PRICE); sim.msgs[shared].refs=2;
    auto id=sim.msgs[shared].id;
    sim.enqueue(event(90,0,1,id,shared)); sim.enqueue(event(90,0,2,id,shared));
    auto one=sim.next_event(); check(one.recipient==1); sim.release(one.slot);
    check(sim.msgs[shared].refs==1);
    int another=sim.pool_message(Message{}); check(another!=shared);
    auto two=sim.next_event(); check(two.recipient==2 && two.msg_id==id); sim.release(two.slot);
    check(sim.msgs[shared].refs==0 && sim.free_slots.back()==shared);
    // Changing computation delay affects subsequent sends; delay/requeue never changes t_recv.
    sim.comp_delays={3,5}; sim.current_time=200; sim.has_causal=true; sim.causal=123;
    sim.P.lat_model=LAT_CONSTANT; sim.P.lat_min=0; sim.P.lat_max=100; sim.P.lat_mean=7;
    slot=sim.new_msg(MT_MKT_HOURS); sim.send(0,1,slot);
    sim.comp_delays[0]=0; slot=sim.new_msg(MT_MKT_HOURS); sim.send(0,1,slot);
    auto early=sim.next_event(); auto late=sim.next_event();
    check(early.t_send==200 && early.t_recv==207 && late.t_send==203 && late.t_recv==210);
    check(early.causal==123 && late.causal==123);
    // Differential queue model checks arbitrary interleaving and candidate displacement.
    sim.have_pending=false; sim.heap.clear(); sim.free_slots.clear(); sim.msgs.pooled.clear();
    using Key=std::tuple<int64_t,int32_t,int32_t,int64_t>;
    std::map<Key,QEntry> model; std::mt19937 rng(719);
    auto key=[](const QEntry& e){return Key{e.time,e.sender,e.recipient,e.msg_id};};
    auto pop=[&]() {
      auto expected=model.begin()->second; model.erase(model.begin());
      auto actual=sim.next_event(); check(key(actual)==key(expected));
      check(actual.t_send==expected.t_send && actual.t_recv==expected.t_recv && actual.causal==expected.causal);
      const Message& m=sim.msgs[actual.slot]; check(m.order.order_id==actual.msg_id);
      if((rng()%5)==0) {
        actual.time+=rng()%13; sim.materialize(actual,m); model.emplace(key(actual),actual);
      } else sim.release(actual.slot);
    };
    for(int k=0;k<5000;++k) {
      for(unsigned j=0,n=rng()%5;j<n;++j) {
        slot=sim.new_msg(MT_ORDER_ACCEPTED); sim.msgs[slot].refs=1;
        auto mid=sim.msgs[slot].id; sim.msgs[slot].order.order_id=mid;
        auto e=event(rng()%17,rng()%4,rng()%4,mid,slot);
        sim.enqueue(e); model.emplace(key(e),e);
      }
      for(unsigned j=0,n=rng()%4;j<n && !model.empty();++j) pop();
    }
    while(!model.empty()) pop();
    check(!sim.have_pending && sim.heap.empty());
    // Reference guard tests the previous time: exactly one event beyond stop can be popped.
    sim.have_pending=false; sim.heap.clear(); sim.P.stop_time=300; sim.current_time=300;
    slot=sim.new_msg(MT_WAKEUP); sim.msgs[slot].refs=1; sim.enqueue(event(301,1,1,55,slot));
    check(sim.current_time<=sim.P.stop_time); sim.current_time=sim.next_event().time;
    check(sim.current_time==301 && !(sim.current_time<=sim.P.stop_time));
  }
};
} }
int main(){ t3::ProtocolProbe::test(); std::cout << "protocol isolated invariants passed\n"; }
