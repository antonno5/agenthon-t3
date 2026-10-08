// Focused checks of the actual CLI hashing function and its error paths.
#include "sha256.hpp"
#include <cassert>
#include <iostream>
#include <filesystem>
#include <fstream>
int main(int argc, char** argv) {
  assert(argc == 2);
  t3cli::Sha256 empty;
  assert(empty.finish() == "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855");
  t3cli::Sha256 abc; abc.update("a", 1); abc.update("bc", 2);
  assert(abc.finish() == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
  std::filesystem::path root(argv[1]); std::filesystem::create_directories(root);
  auto file = root / "sha-million-a";
  { std::ofstream f(file, std::ios::binary); f << std::string(1000000, 'a'); }
  assert(t3cli::sha256_file(file.string()) == "cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0");
  std::filesystem::remove(file);
  bool missing = false; try { t3cli::sha256_file(file.string()); } catch (const std::runtime_error&) { missing = true; }
  assert(missing);
  bool directory = false; try { t3cli::sha256_file(root.string()); } catch (const std::runtime_error&) { directory = true; }
  assert(directory);
  std::cout << "hash_checks=5 provider=" << t3cli::Sha256().provider() << " openssl=" << OpenSSL_version(0) << '\n';
}
