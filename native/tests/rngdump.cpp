// Test helper: replays a script of RandomState calls and prints each result (%.17g).
// stdin: "seed S" then lines "op arg1 arg2" ; ops: n(ormal) l(ognormal) u(niform) e(xponential)
// p(areto) r(andint low high) w (randint_u32_full) d (next_double)
#include <cstdio>
#include <cstring>
#include "../rng.hpp"
int main() {
  char op[16];
  double a, b;
  t3::RandomState rs(0);
  while (scanf("%15s %lf %lf", op, &a, &b) == 3) {
    switch (op[0]) {
      case 's': rs.seed((uint32_t)(unsigned long long)a); break;
      case 'n': printf("%.17g\n", rs.normal(a, b)); break;
      case 'l': printf("%.17g\n", rs.lognormal(a, b)); break;
      case 'u': printf("%.17g\n", rs.uniform(a, b)); break;
      case 'e': printf("%.17g\n", rs.exponential(a)); break;
      case 'p': printf("%.17g\n", rs.pareto(a)); break;
      case 'r': printf("%lld\n", (long long)rs.randint((long long)a, (long long)b)); break;
      case 'w': printf("%u\n", rs.randint_u32_full()); break;
      case 'd': printf("%.17g\n", rs.next_double()); break;
    }
  }
}
