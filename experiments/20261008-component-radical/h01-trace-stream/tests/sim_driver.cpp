// Executive summary: dump all lifecycle and message columns from one unmodified native engine.
#include "engine.hpp"
#include "read_params.hpp"
#include <fstream>
#include <iostream>
#include <stdexcept>
using namespace t3;
template<class T> void write(std::ostream& out,const std::vector<T>& v) {
  const uint64_t n=v.size(); out.write(reinterpret_cast<const char*>(&n),sizeof(n));
  out.write(reinterpret_cast<const char*>(v.data()),v.size()*sizeof(T));
}
int main(int argc,char** argv) {
  if(argc!=3) return 2;
  const auto p=read_params(argv[1]);
  const auto r=run(p); std::ofstream out(argv[2],std::ios::binary);
  const auto& t=r.trace;const auto& m=r.messages;
  write(out,t.t_ns);write(out,t.agent_id);write(out,t.msg_type);write(out,t.side);
  write(out,t.price);write(out,t.size);write(out,t.order_id);
  write(out,m.t_recv);write(out,m.t_send);write(out,m.latency);write(out,m.message_id);
  write(out,m.order_id);write(out,m.causal_parent);write(out,m.t_send_null);
  write(out,m.order_id_null);write(out,m.causal_null);write(out,m.src);write(out,m.dst);write(out,m.msg_type);
  std::cout<<"{\"trace_rows\":"<<t.t_ns.size()<<",\"message_rows\":"<<r.n_messages<<"}\n";
}
