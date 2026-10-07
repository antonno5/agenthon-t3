// Minimal SHA-256 (FIPS 180-4) for hashing the output files without importing hashlib.
#pragma once
#include <string>
namespace t3 {
// Lowercase hex digest of the file's bytes; throws std::runtime_error if unreadable.
std::string sha256_file(const std::string& path);
}  // namespace t3
