// Differential state-machine test against a deliberately simple sorted vector.
#include "book.hpp"
#include <iostream>
#include <map>
#include <random>
#include <stdexcept>
using namespace t3;
void check(bool value) { if (!value) throw std::runtime_error("book invariant mismatch"); }
void compare(const PriceSide& s, const std::map<int64_t,std::deque<Order>>& ref, bool bid) {
  check(s.valid()); check(s.size()==ref.size());
  size_t i=0;
  auto level=[&](const auto& kv) {
    const auto& l=s[i++]; check(l.price==kv.first); check(l.orders.size()==kv.second.size());
    int64_t total=0;
    for (size_t j=0;j<kv.second.size();++j) {
      check(l.orders[j].order_id==kv.second[j].order_id);
      check(l.orders[j].quantity==kv.second[j].quantity); total+=kv.second[j].quantity;
    }
    check(l.total==total);
  };
  if (bid) for(auto it=ref.rbegin();it!=ref.rend();++it) level(*it);
  else for (const auto& kv:ref) level(kv);
}
int main() {
  for (bool bid:{false,true}) {
    PriceSide s(bid); std::map<int64_t,std::deque<Order>> ref;
    std::mt19937 rng(71); int64_t oid=0;
    for(int k=0;k<40000;++k) {
      const int op=rng()%4;
      if(op<2 || ref.empty()) {
        Order o{oid++,1,static_cast<int8_t>(bid?1:-1),static_cast<int64_t>(rng()%512),1+static_cast<int64_t>(rng()%30)};
        s.enter(o); ref[o.limit_price].push_back(o);
      } else if(op==2) {
        auto it=ref.begin(); std::advance(it,rng()%ref.size());
        auto& q=it->second; size_t j=rng()%q.size(); Order want=q[j],removed;
        check(s.cancel(want,removed)); check(removed.quantity==want.quantity);
        q.erase(q.begin()+j); if(q.empty()) ref.erase(it);
        check(!s.cancel(want,removed));
      } else {
        auto it=bid?std::prev(ref.end()):ref.begin();
        const int64_t amount=1+rng()%30; auto& q=it->second;
        Order expected=q.front(); expected.quantity=std::min(expected.quantity,amount);
        Order got=s.take_best(amount); check(got.order_id==expected.order_id); check(got.quantity==expected.quantity);
        q.front().quantity-=expected.quantity; if(q.front().quantity==0) q.pop_front();
        if(q.empty()) ref.erase(it);
      }
      compare(s,ref,bid);
      int64_t p=rng()%512; size_t position=0;
      if(bid) for(auto it=ref.rbegin();it!=ref.rend() && it->first>p;++it) ++position;
      else for(auto it=ref.begin();it!=ref.end() && it->first<p;++it) ++position;
      check(s.position(p)==position);
    }
    // Exhaust the book to exercise compaction, then reuse/reset its prefix.
    while(!s.empty()) { s.take_best(INT64_MAX); check(s.valid()); }
    check(s.storage_size()==0); check(s.discarded_prefix()==0);
    for(int i=0;i<512;++i) s.enter(Order{i,1,static_cast<int8_t>(bid?1:-1),bid?512-i:i,1});
    for(int i=0;i<63;++i) s.take_best(1);
    check(s.discarded_prefix()==63);
    auto storage=s.storage_size(); auto price=s[0].price+(bid?1:-1);
    s.enter(Order{1000,1,static_cast<int8_t>(bid?1:-1),price,2});
    check(s.discarded_prefix()==62); check(s.storage_size()==storage); check(s.valid());
  }
  std::cout << "PASS: 80,000 differential mutations, FIFO, binary positions, aggregate volumes, prefix reuse and compaction\n";
}
