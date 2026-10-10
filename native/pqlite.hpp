// Dependency-free Parquet writer for the two journals (no Arrow/Parquet libraries, no
// OpenSSL). Produces files whose DECODED content -- Arrow schema incl. the pandas and
// ARROW:schema metadata, row count, and every value in order -- equals what the pinned
// Arrow 15 writer produced (verified: tools/pqlite_check.py on all public units + fuzzing).
//
// Layout per file: one row group; per column one chunk of Snappy-compressed V1 data pages
// (definition levels RLE/bit-packed; numbers PLAIN; the string vocabularies msg_type and
// side dictionary-encoded with a PLAIN dictionary page). No statistics. Footer in the
// Thrift compact protocol. Files are hashed (SHA-256) as they are written, so no re-read is
// needed for events.json. The streaming writers (TraceWriter, MessageWriter) write one row
// group per 64K rows while the run goes on, from a writer thread; only the last row group,
// the trace's msg_type chunks (placed after all the others) and the footer are left for close().
#pragma once

#include <memory>
#include <string>

#include "engine.hpp"

namespace t3 {
namespace pqlite {

// Streams the message ledger: append() encodes and compresses one block as a row group (one
// page per column, columns in parallel) and queues it for writing; close() adds the footer and
// returns the file's SHA-256 hex.
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

// The same table, written while the trace is built: rows_final() encodes every complete page of
// the columns that are already final (all but msg_type) as a row group and queues it for
// writing; close() encodes the rest and finishes the file. Decodes exactly as write_trace()'s.
class TraceWriter final : public TraceSink {
 public:
  explicit TraceWriter(std::string path);
  ~TraceWriter() override;
  size_t rows_final(const TraceColumns& cols, size_t n) override;
  std::string close(const TraceColumns& t);

 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};

}  // namespace pqlite
}  // namespace t3
