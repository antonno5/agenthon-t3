Executive summary: this library lets the standalone executable read JSON without
an interpreter or runtime downloads. SHA256 uses the pinned runtime's OpenSSL EVP
provider, shared with Python hashlib, through the public ABI in `../sha256.hpp`.

- nlohmann/json v3.11.3, `single_include/nlohmann/json.hpp`, MIT:
  https://github.com/nlohmann/json/tree/v3.11.3

The source header is unmodified; standalone license whitespace is normalized. SHA-256 values are recorded in the
experiment source manifest. JSON integers retain 64-bit precision; parameters are
translated with the existing adapter's defaults and bounds.
