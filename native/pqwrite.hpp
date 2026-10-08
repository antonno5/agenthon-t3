// Writes both journals with exact decoded values and schemas from the pinned
// pandas/Arrow15 contract. Physical encoding follows the frozen H01 policy.
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
