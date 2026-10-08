// Dependency-free Parquet writer for the two journals (no Arrow/Parquet libraries, no
// OpenSSL). Produces files whose DECODED content -- Arrow schema incl. the pandas and
// ARROW:schema metadata, row count, and every value in order -- equals what the pinned
// Arrow 15 writer produced (verified: tools/pqlite_check.py on all public units + fuzzing).
//
// Layout per file: one row group; per column one chunk of Snappy-compressed V1 data pages
// (definition levels RLE/bit-packed; numbers PLAIN; the string vocabularies msg_type and
// side dictionary-encoded with a PLAIN dictionary page). No statistics. Footer in the
// Thrift compact protocol. The whole file is built in memory, hashed (SHA-256) and written
// in one pass, so no re-read is needed for events.json.
#pragma once

#include <memory>
#include <string>

#include "engine.hpp"

namespace t3 {
namespace pqlite {

// Streams the message ledger: append() encodes and compresses one block as one page per
// column (columns in parallel); close() writes the file and returns its SHA-256 hex.
class MessageWriter {
 public:
  explicit MessageWriter(std::string path);
  ~MessageWriter();
  void append(const MessageColumns& m, size_t seq_offset);
  std::string close();

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

// Writes trace.parquet; returns its SHA-256 hex.
std::string write_trace(const TraceColumns& t, const std::string& path);

}  // namespace pqlite
}  // namespace t3
