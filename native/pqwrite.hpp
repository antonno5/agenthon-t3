// Writes the engine's columns as trace.parquet / message_trace.parquet, byte-identical to
// pandas.DataFrame.to_parquet(compression="snappy", index=False) on pyarrow 15.0.2.
#pragma once

#include <string>

#include "engine.hpp"

namespace t3 {
void write_trace(const TraceColumns& t, const std::string& path);
void write_messages(const MessageColumns& m, const std::string& path);
}  // namespace t3
