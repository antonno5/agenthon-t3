#include "scenario.hpp"
#include <iostream>
#include <fstream>
// HOST ONLY: ARM host cannot build the production x86 NumPy dispatch. Differential
// mapping tests inject the same libm result into Python; runtime tests use nplog.cpp.
namespace t3 {
bool numpy_log(double x, double* y) { *y = std::log(x); return true; }
const char* numpy_log_dispatch() { return "host-test-libm"; }
}
int main(int argc, char** argv) {
  try {
    std::ifstream f(argv[1]); auto j = t3cli::Json::parse(f);
    if (argc == 3) j["seed"] = std::stoll(argv[2]);
    std::cout << t3cli::describe(t3cli::build(j)).dump() << '\n'; return 0;
  } catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 1; }
}
