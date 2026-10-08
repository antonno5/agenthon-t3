// Standalone front end. Engine, RNG, numpy log and Parquet writer remain unchanged.
#include "scenario.hpp"
#include "message_pipeline.hpp"
#include "pqwrite.hpp"
#include "sha256.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <sys/resource.h>
#include <unistd.h>

namespace {
using t3cli::Json;
using Clock = std::chrono::steady_clock;
double since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }
std::string sha(const std::filesystem::path& p) {
  return t3cli::sha256_file(p.string());
}
void write_json(const std::filesystem::path& path, const Json& j) {
  std::ofstream f(path); f << j.dump(2) << '\n'; f.close();
  if (!f) throw std::runtime_error("cannot write " + path.string());
}
int fallback(int argc, char** argv, bool batch = false) {
  std::vector<std::string> args = {"python", "-m", batch ? "abides_fork.simulate_batch" : "abides_fork.simulate"};
  for (int i = 1; i < argc; ++i) {
    if (i == 1 && (std::string(argv[i]) == "simulate" || std::string(argv[i]) == "simulate-batch")) continue;
    args.emplace_back(argv[i]);
  }
  std::vector<char*> raw;
  for (auto& a : args) raw.push_back(a.data());
  raw.push_back(nullptr);
  execvp(raw[0], raw.data()); throw std::runtime_error("cannot execute original Python adapter");
}
struct StagedMessage {
  std::string path;
  explicit StagedMessage(const std::string& target) {
    std::string pattern = target + ".pipeline-XXXXXX";
    std::vector<char> name(pattern.begin(), pattern.end()); name.push_back(0);
    int fd = mkstemp(name.data());
    if (fd < 0) throw std::runtime_error("cannot create staged message parquet");
    ::close(fd); path = name.data();
  }
  ~StagedMessage() { std::remove(path.c_str()); }
};
struct Output { size_t events, messages; double seconds; };
Output run_write(t3::Params p, const std::string& trace, const std::string& msg) {
  // Keep the same pipeline, stage/publish order and measurement boundary as module.cpp.
  std::unique_ptr<StagedMessage> staged;
  std::unique_ptr<t3::MessageParquetWriter> writer;
  t3::MessagePipeline pipeline([&](const t3::MessageColumns& block, size_t offset) {
    if (!writer) { staged = std::make_unique<StagedMessage>(msg); writer = std::make_unique<t3::MessageParquetWriter>(staged->path); }
    writer->append(block, offset);
  }, [&] {
    if (!writer) { staged = std::make_unique<StagedMessage>(msg); writer = std::make_unique<t3::MessageParquetWriter>(staged->path); }
    writer->close();
  });
  auto t0 = Clock::now(); auto r = t3::run(std::move(p), &pipeline); double seconds = since(t0);
  if (r.trace.t_ns.empty()) { pipeline.cancel(); throw t3cli::Unsupported("empty trace requires original adapter dtypes"); }
  t3::write_trace(r.trace, trace); pipeline.finish();
  if (std::rename(staged->path.c_str(), msg.c_str()) != 0) throw std::runtime_error("cannot publish staged message parquet");
  return {r.trace.t_ns.size(), r.n_messages, seconds};
}
}
int main(int argc, char** argv) {
  try {
    if ((argc > 1 && std::string(argv[1]) == "simulate-batch") ||
        std::filesystem::path(argv[0]).filename() == "simulate-batch") return fallback(argc, argv, true);
    std::string config, out, seed; bool dump = false, strict = false, has_seed = false;
    const char* env_engine = std::getenv("T3_ENGINE");
    const char* required = std::getenv("T3_REQUIRE_NATIVE");
    strict = (env_engine && std::string(env_engine) == "native") || (required && std::string(required) == "1");
    if (env_engine && std::string(env_engine) == "python") return fallback(argc, argv);
    for (int i = 1; i < argc; ++i) {
      std::string a = argv[i]; if (i == 1 && a == "simulate") continue;
      if (a == "--help" || a == "-h") {
        std::cout << "simulate --config FILE --out FILE [--seed INTEGER] [--trace-mode buffered] [--engine auto|native|python]\n";
        return 0;
      }
      if (a == "--dump-native-config") { dump = true; continue; }
      if (a == "--profile-components") return fallback(argc, argv);
      if (i + 1 >= argc) throw std::runtime_error("missing argument for " + a);
      std::string v = argv[++i];
      if (a == "--config") config = v;
      else if (a == "--out") out = v;
      else if (a == "--seed") { seed = v; has_seed = true; }
      else if (a == "--trace-mode") {
        if (v == "legacy" || v == "verify") return fallback(argc, argv);
        if (v != "buffered") throw std::runtime_error("unknown trace mode");
      } else if (a == "--engine") {
        if (v == "python") return fallback(argc, argv);
        if (v != "native" && v != "auto") throw std::runtime_error("unknown engine");
        strict = v == "native" || (required && std::string(required) == "1");
      } else return fallback(argc, argv);
    }
    if (config.empty() || (out.empty() && !dump)) throw std::runtime_error("--config and --out required");
    auto started = Clock::now();
    std::ifstream file(config);
    if (!file) return fallback(argc, argv); // retain batch/missing-file diagnostic
    Json scenario;
    try { file >> scenario; } catch (...) { return fallback(argc, argv); }
    if (has_seed) {
      // Python argparse's broader integer syntax is handled by the original adapter.
      size_t n = 0;
      try { auto v = std::stoll(seed, &n); if (n != seed.size()) return fallback(argc, argv); scenario["seed"] = v; }
      catch (...) { return fallback(argc, argv); }
    }
    t3::Params params;
    try { params = t3cli::build(scenario); }
    catch (...) { if (dump || strict) throw; return fallback(argc, argv); }
    if (dump) { std::cout << t3cli::describe(params).dump() << '\n'; return 0; }
    // Python str(scenario_id) admits additional types; delegate them before running.
    if (!scenario.contains("scenario_id") || !scenario["scenario_id"].is_string()) {
      if (strict) throw t3cli::Unsupported("scenario_id requires Python conversion");
      return fallback(argc, argv);
    }
    std::filesystem::path trace(out), parent = trace.parent_path();
    if (parent.empty()) parent = ".";
    std::filesystem::create_directories(parent);
    auto msg = parent / "message_trace.parquet";
    double configured = since(started); Output result;
    try { result = run_write(std::move(params), trace.string(), msg.string()); }
    catch (const std::runtime_error&) { if (strict) throw; return fallback(argc, argv); }
    double written = since(started);
    auto trace_hash = sha(trace), message_hash = sha(msg);
    struct rusage usage{}; if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("getrusage failed");
    auto peak = static_cast<int64_t>(usage.ru_maxrss) * 1024;
    Json ev = {{"scenario_id", scenario["scenario_id"]}, {"seed", scenario["seed"]},
      {"n_events", result.events}, {"n_messages", result.messages}, {"engine", "native"},
      {"trace_sha256", trace_hash}, {"message_trace_sha256", message_hash}, {"peak_memory_bytes", peak},
      {"gpu_seconds", 0.0}, {"simulation_wall_clock_sec", result.seconds}};
    ev["wall_clock_sec"] = since(started); ev["events_per_sec"] = result.events / ev["wall_clock_sec"].get<double>();
    write_json(parent / "events.json", ev);
    Json profile = {{"schema_version", 1}, {"engine", "native"}, {"trace_mode", "buffered"},
      {"detailed", false}, {"timing_kind", "wall_clock_phases"}, {"wall_clock_sec", ev["wall_clock_sec"]},
      {"phases", {{"configuration", configured}, {"simulation_and_trace_finalize", result.seconds},
        {"parquet_write", std::max(0.0, written - configured - result.seconds)},
        {"hashing", ev["wall_clock_sec"].get<double>() - written}}},
      {"components", Json::object()}, {"simulation_components", Json::object()}, {"component_calls", Json::object()},
      {"gpu_utilization", 0.0}, {"peak_memory_bytes", peak},
      {"native_executable", true}, {"numpy_log_dispatch", t3::numpy_log_dispatch()},
      {"hash_provider", t3cli::Sha256().provider()}, {"openssl_version", OpenSSL_version(0)}};
    write_json(parent / "profile.json", profile);
    ev["wall_clock_sec"] = since(started); ev["events_per_sec"] = result.events / ev["wall_clock_sec"].get<double>();
    write_json(parent / "events.json", ev); std::cout << ev.dump() << '\n'; return 0;
  } catch (const std::exception& e) { std::cerr << "simulate: " << e.what() << '\n'; return 1; }
}
