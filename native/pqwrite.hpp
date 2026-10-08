// Writes the engine's columns as trace.parquet / message_trace.parquet, byte-identical to
// pandas.DataFrame.to_parquet(compression="snappy", index=False) on pyarrow 15.0.2.
#pragma once

#include <string>
#include <memory>

#include "engine.hpp"

namespace t3 {
// Encode aligned blocks in one buffered row group; flush at canonical 1Mi boundaries.
class MessageParquetWriter {
 public:
  explicit MessageParquetWriter(const std::string& path);
  ~MessageParquetWriter();
  void append(const MessageColumns& m, size_t seq_offset);
  void close();
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
void write_trace(const TraceColumns& t, const std::string& path);
void write_messages(const MessageColumns& m, const std::string& path);
}  // namespace t3
