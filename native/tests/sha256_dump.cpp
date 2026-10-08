#include "../sha256_lite.hpp"
#include <cstdio>
#include <vector>
int main() { std::vector<uint8_t> in; int c; while ((c = getchar()) != EOF) in.push_back((uint8_t)c);
  t3::sha256_lite::Sha256 s; size_t i = 0, step = 1;  // feed in uneven pieces
  while (i < in.size()) { size_t k = std::min(step, in.size() - i); s.update(in.data() + i, k); i += k; step = step * 3 % 1000 + 1; }
  printf("%s %s\n", s.hex().c_str(), t3::sha256_lite::Sha256::provider()); }
