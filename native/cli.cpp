// Standalone front end. Engine, RNG, numpy log and Parquet writer remain unchanged.
#include "scenario.hpp"
#include "message_pipeline.hpp"
#include "pqlite.hpp"
#include "sha256_lite.hpp"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <algorithm>
#include <memory>
#include <optional>
#include <thread>
#include <sys/resource.h>
#include <unistd.h>

namespace {
using t3cli::Json;
using Clock = std::chrono::steady_clock;
double since(Clock::time_point t) { return std::chrono::duration<double>(Clock::now() - t).count(); }
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
struct Output { size_t events, messages; double seconds; std::string trace_hash, message_hash; };
Output run_write(t3::Params p, const std::string& trace, const std::string& msg) {
  // The ledger streams into a staged file while the kernel runs (pages are compressed on the
  // pipeline thread); the lifecycle trace is written after the run. Both writers build the
  // file in memory and return its SHA-256, so neither file is read back for events.json.
  std::unique_ptr<StagedMessage> staged;
  std::unique_ptr<t3::pqlite::MessageWriter> writer;
  std::string message_hash;
  t3::MessagePipeline pipeline([&](const t3::MessageColumns& block, size_t offset) {
    if (!writer) { staged = std::make_unique<StagedMessage>(msg); writer = std::make_unique<t3::pqlite::MessageWriter>(staged->path); }
    writer->append(block, offset);
  }, [&] {
    if (!writer) { staged = std::make_unique<StagedMessage>(msg); writer = std::make_unique<t3::pqlite::MessageWriter>(staged->path); }
    message_hash = writer->close();
  });
  auto t0 = Clock::now(); auto r = t3::run(std::move(p), &pipeline); double seconds = since(t0);
  if (r.trace.t_ns.empty()) { pipeline.cancel(); throw t3cli::Unsupported("empty trace requires original adapter dtypes"); }
  std::string trace_hash = t3::pqlite::write_trace(r.trace, trace); pipeline.finish();
  if (std::rename(staged->path.c_str(), msg.c_str()) != 0) throw std::runtime_error("cannot publish staged message parquet");
  return {r.trace.t_ns.size(), r.n_messages, seconds, trace_hash, message_hash};
}

// Python-equivalent result of one `simulate` run on the native path, or nullopt when the
// original adapter must handle it (unsupported scenario, conversion or engine refusal).
// Writes trace.parquet, message_trace.parquet, events.json and profile.json next to `out`.
std::optional<Json> run_scenario(const std::string& config, const std::string& out,
                                 const std::optional<std::string>& seed, bool strict) {
  auto started = Clock::now();
  std::ifstream file(config);
  if (!file) return std::nullopt;  // retain batch/missing-file diagnostic
  Json scenario;
  try { file >> scenario; } catch (...) { return std::nullopt; }
  if (seed) {
    // Python argparse's broader integer syntax is handled by the original adapter.
    size_t n = 0;
    try { auto v = std::stoll(*seed, &n); if (n != seed->size()) return std::nullopt; scenario["seed"] = v; }
    catch (...) { return std::nullopt; }
  }
  t3::Params params;
  try { params = t3cli::build(scenario); }
  catch (...) { if (strict) throw; return std::nullopt; }
  // Python str(scenario_id) admits additional types; delegate them before running.
  if (!scenario.contains("scenario_id") || !scenario["scenario_id"].is_string()) {
    if (strict) throw t3cli::Unsupported("scenario_id requires Python conversion");
    return std::nullopt;
  }
  std::filesystem::path trace(out), parent = trace.parent_path();
  if (parent.empty()) parent = ".";
  std::filesystem::create_directories(parent);
  auto msg = parent / "message_trace.parquet";
  double configured = since(started); Output result;
  try { result = run_write(std::move(params), trace.string(), msg.string()); }
  catch (const std::runtime_error&) { if (strict) throw; return std::nullopt; }
  double written = since(started);
  const std::string& trace_hash = result.trace_hash;  // computed while writing
  const std::string& message_hash = result.message_hash;
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
    {"hash_provider", t3::sha256_lite::Sha256::provider()}, {"parquet_writer", "pqlite"}};
  write_json(parent / "profile.json", profile);
  ev["wall_clock_sec"] = since(started); ev["events_per_sec"] = result.events / ev["wall_clock_sec"].get<double>();
  write_json(parent / "events.json", ev);
  return ev;
}

// `simulate-batch --batch-dir DIR --out-dir DIR` on the native path: the same sub order,
// per-sub outputs and batch_events.json as abides_fork.simulate_batch. Anything the native
// path cannot run hands the whole batch to the original adapter (which rewrites every sub).
int batch_main(int argc, char** argv) {
  std::string batch_dir, out_dir;
  const char* env_engine = std::getenv("T3_ENGINE");
  const char* required = std::getenv("T3_REQUIRE_NATIVE");
  const bool strict = (env_engine && std::string(env_engine) == "native") || (required && std::string(required) == "1");
  if (env_engine && std::string(env_engine) == "python") return fallback(argc, argv, true);
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i]; if (i == 1 && a == "simulate-batch") continue;
    if (i + 1 >= argc) return fallback(argc, argv, true);  // argparse owns usage/errors
    std::string v = argv[++i];
    if (a == "--batch-dir") batch_dir = v;
    else if (a == "--out-dir") out_dir = v;
    else if (a == "--trace-mode" && v == "buffered") continue;
    else return fallback(argc, argv, true);
  }
  if (batch_dir.empty() || out_dir.empty()) return fallback(argc, argv, true);
  // pathlib.Path(batch_dir).glob("*.json"), sorted: names ending in ".json" (directories
  // included, as glob does; the per-sub run then refuses them and the batch is delegated).
  std::vector<std::string> names;
  try {
    for (const auto& e : std::filesystem::directory_iterator(batch_dir)) {
      const std::string n = e.path().filename().string();
      if (n.size() >= 5 && n.compare(n.size() - 5, 5, ".json") == 0) names.push_back(n);
    }
  } catch (...) { return fallback(argc, argv, true); }
  if (names.empty()) return fallback(argc, argv, true);  // the adapter's SystemExit message
  std::sort(names.begin(), names.end());
  nlohmann::ordered_json per_scenario = nlohmann::ordered_json::array();
  int64_t total_events = 0, peak_memory = 0;
  double gpu_seconds = 0.0;
  auto t0 = Clock::now();
  for (const auto& name : names) {
    const std::string sub = name.substr(0, name.size() - 5);
    const auto sub_out = (std::filesystem::path(out_dir) / sub / "trace.parquet").string();
    std::optional<Json> ev;
    try { ev = run_scenario((std::filesystem::path(batch_dir) / name).string(), sub_out, std::nullopt, strict); }
    catch (...) { if (strict) throw; ev = std::nullopt; }
    if (!ev) return fallback(argc, argv, true);
    total_events += (*ev)["n_events"].get<int64_t>();
    peak_memory = std::max<int64_t>(peak_memory, (*ev)["peak_memory_bytes"].get<int64_t>());
    gpu_seconds += (*ev)["gpu_seconds"].get<double>();
    nlohmann::ordered_json entry;
    entry["sub"] = sub;
    entry["n_events"] = (*ev)["n_events"];
    entry["trace_sha256"] = (*ev)["trace_sha256"];
    per_scenario.push_back(entry);
  }
  const double wall = since(t0);
  nlohmann::ordered_json agg;  // key order of the adapter's dict
  agg["n_scenarios"] = names.size();
  agg["total_events"] = total_events;
  agg["wall_clock_sec"] = wall;
  agg["events_per_sec"] = wall > 0 ? total_events / wall : 0.0;
  agg["peak_memory_bytes"] = peak_memory;
  agg["gpu_seconds"] = gpu_seconds;
  agg["per_scenario"] = per_scenario;
  std::filesystem::create_directories(out_dir);
  {
    std::ofstream f(std::filesystem::path(out_dir) / "batch_events.json");
    f << agg.dump(2) << '\n'; f.close();
    if (!f) throw std::runtime_error("cannot write batch_events.json");
  }
  std::cout << agg.dump() << '\n';
  return 0;
}
}  // namespace

int main(int argc, char** argv) {
  try {
    if ((argc > 1 && std::string(argv[1]) == "simulate-batch") ||
        std::filesystem::path(argv[0]).filename() == "simulate-batch") return batch_main(argc, argv);
    std::string config, out; std::optional<std::string> seed; bool dump = false, strict = false;
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
      else if (a == "--seed") seed = v;
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
    if (dump) {
      std::ifstream file(config);
      if (!file) return fallback(argc, argv);
      Json scenario; file >> scenario;
      if (seed) scenario["seed"] = std::stoll(*seed);
      std::cout << t3cli::describe(t3cli::build(scenario)).dump() << '\n';
      return 0;
    }
    auto ev = run_scenario(config, out, seed, strict);
    if (!ev) return fallback(argc, argv);
    std::cout << ev->dump() << '\n'; return 0;
  } catch (const std::exception& e) { std::cerr << "simulate: " << e.what() << '\n'; return 1; }
}
