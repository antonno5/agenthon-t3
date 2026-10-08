// Minimal OpenSSL 3 public EVP ABI declarations. The pinned wheel runtime ships
// libcrypto.so.3 but no development headers. These opaque types/signatures match
// include/openssl/{types.h,evp.h,crypto.h,provider.h} in OpenSSL 3.5.7.
// No hashing implementation is vendored: use the same fetched SHA256 provider as
// CPython _hashlib (usedforsecurity=True, default library context/properties).
#pragma once
#include <cstddef>
#include <fstream>
#include <memory>
#include <stdexcept>
#include <string>

extern "C" {
typedef struct evp_md_ctx_st EVP_MD_CTX;
typedef struct evp_md_st EVP_MD;
typedef struct engine_st ENGINE;
typedef struct ossl_lib_ctx_st OSSL_LIB_CTX;
typedef struct ossl_provider_st OSSL_PROVIDER;
EVP_MD_CTX* EVP_MD_CTX_new(void);
void EVP_MD_CTX_free(EVP_MD_CTX*);
EVP_MD* EVP_MD_fetch(OSSL_LIB_CTX*, const char*, const char*);
void EVP_MD_free(EVP_MD*);
int EVP_DigestInit_ex(EVP_MD_CTX*, const EVP_MD*, ENGINE*);
int EVP_DigestUpdate(EVP_MD_CTX*, const void*, size_t);
int EVP_DigestFinal_ex(EVP_MD_CTX*, unsigned char*, unsigned int*);
const OSSL_PROVIDER* EVP_MD_get0_provider(const EVP_MD*);
const char* OSSL_PROVIDER_get0_name(const OSSL_PROVIDER*);
const char* OpenSSL_version(int);
}
namespace t3cli {
class Sha256 {
 public:
  Sha256() : md_(EVP_MD_fetch(nullptr, "SHA256", nullptr), EVP_MD_free),
             ctx_(EVP_MD_CTX_new(), EVP_MD_CTX_free) {
    if (!md_ || !ctx_ || EVP_DigestInit_ex(ctx_.get(), md_.get(), nullptr) != 1)
      throw std::runtime_error("OpenSSL SHA256 initialization failed");
  }
  void update(const void* data, size_t size) {
    if (EVP_DigestUpdate(ctx_.get(), data, size) != 1)
      throw std::runtime_error("OpenSSL SHA256 update failed");
  }
  std::string finish() {
    unsigned char digest[32]; unsigned int size = 0;
    if (EVP_DigestFinal_ex(ctx_.get(), digest, &size) != 1 || size != sizeof digest)
      throw std::runtime_error("OpenSSL SHA256 finalization failed");
    const char* hex = "0123456789abcdef"; std::string result;
    result.reserve(64);
    for (unsigned char c : digest) { result += hex[c >> 4]; result += hex[c & 15]; }
    return result;
  }
  const char* provider() const {
    auto p = EVP_MD_get0_provider(md_.get());
    if (!p) throw std::runtime_error("SHA256 has no fetched OpenSSL provider");
    return OSSL_PROVIDER_get0_name(p);
  }
 private:
  std::unique_ptr<EVP_MD, decltype(&EVP_MD_free)> md_;
  std::unique_ptr<EVP_MD_CTX, decltype(&EVP_MD_CTX_free)> ctx_;
};
inline std::string sha256_file(const std::string& path) {
  std::ifstream file(path, std::ios::binary);
  if (!file) throw std::runtime_error("cannot hash " + path);
  Sha256 h; char block[1 << 20]; // original simulate.py reads the same block size
  while (file) { file.read(block, sizeof block); h.update(block, static_cast<size_t>(file.gcount())); }
  if (!file.eof()) throw std::runtime_error("hash read failed: " + path);
  return h.finish();
}
} // namespace t3cli
