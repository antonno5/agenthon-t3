#include "../snappy_lite.hpp"
#include <cstdio>
int main() {  // stdin -> compressed stdout
  std::vector<uint8_t> in; int c; while ((c = getchar()) != EOF) in.push_back((uint8_t)c);
  std::vector<uint8_t> out; t3::snappy_lite::compress(in.data(), in.size(), out);
  fwrite(out.data(), 1, out.size(), stdout);
}
