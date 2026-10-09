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
#include <atomic>
#include <memory>
#include <optional>
#include <thread>
#include <sys/resource.h>
#include <unistd.h>

// Present only in the profile-training build (-fprofile-generate), where _exit would otherwise
// drop the counts; a weak reference resolves to null in every other build.
extern "C" void __gcov_dump() __attribute__((weak));
[[noreturn]] void t3_exit(int code) {
  if (__gcov_dump) __gcov_dump();
  _exit(code);
}
#define T3_EXIT(code) t3_exit(code)

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
  execvp(raw[0], raw.data());
  throw std::runtime_error("this scenario needs the Python adapter, which this image does not contain");
}
struct Output { size_t events, messages; double seconds; std::string trace_hash, message_hash; };
// `msg` empty: no ledger (the card does not require one), so no ledger file, thread or rows.
Output run_write(t3::Params p, const std::string& trace, const std::string& msg) {
  // The ledger streams into its file while the kernel runs (pages are compressed on the
  // pipeline thread); the lifecycle trace is written after the run. Both writers build the
  // file in memory and return its SHA-256, so neither file is read back for events.json.
  std::unique_ptr<t3::pqlite::MessageWriter> writer;
  std::string message_hash;
  std::unique_ptr<t3::MessagePipeline> pipeline;
  p.ledger = !msg.empty();
  if (p.ledger)
    pipeline = std::make_unique<t3::MessagePipeline>([&](const t3::MessageColumns& block, size_t offset) {
      if (!writer) writer = std::make_unique<t3::pqlite::MessageWriter>(msg);
      writer->append(block, offset);
    }, [&] {
      if (!writer) writer = std::make_unique<t3::pqlite::MessageWriter>(msg);
      message_hash = writer->close();
    });
  // The result (multi-MB columns) and the ledger writer's page buffers are deliberately never
  // freed: the process exits right after writing its outputs, and freeing them (munmap of
  // large blocks) would only add wall time to the run.
  // The trace's final columns are encoded into pages while the kernel still runs.
  auto& trace_writer = *new t3::pqlite::TraceWriter(trace);
  auto t0 = Clock::now(); auto& r = *new t3::Result(t3::run(std::move(p), pipeline.get(), &trace_writer)); double seconds = since(t0);
  if (r.trace.t_ns.empty()) {
    if (pipeline) pipeline->cancel();
    throw t3cli::Unsupported("empty trace requires original adapter dtypes");
  }
  if (pipeline) pipeline->close_async();  // the ledger file is finished on its own thread meanwhile
  std::string trace_hash = trace_writer.close(r.trace);
  if (pipeline) pipeline->finish();
  (void)writer.release();  // keep its page buffers alive until _exit (see above)
  return {r.trace.t_ns.size(), r.n_messages, seconds, trace_hash, message_hash};
}

// Python-equivalent result of one `simulate` run on the native path, or nullopt when the
// original adapter must handle it (unsupported scenario, conversion or engine refusal).
// Writes trace.parquet, message_trace.parquet, events.json and profile.json next to `out`.
// Whether the unit's card.toml beside the config makes the message ledger optional, by the
// scorer's own rule (limits.requires_message_ledger): `[scoring.params] requires_message_ledger`
// when it is a boolean, else required unless `[task] scenario_family = "throughput-scale"`.
// README: "don't write message_trace.parquet on units whose card has requires_message_ledger =
// false". Only plain `key = value` lines are read; no card, a batch card, or any mention of the
// key we did not read as a [scoring.params] boolean keeps the ledger.
// Off by default: the ledger is always written unless T3_LEDGER_FROM_CARD=1 (the Development
// score of the image that skipped it dropped unexplained, 190 -> 181 thousand).
bool ledger_optional(const std::string& config) {
  const char* from_card = std::getenv("T3_LEDGER_FROM_CARD");
  if (!from_card || std::string(from_card) != "1") return false;
  std::ifstream f(std::filesystem::path(config).parent_path() / "card.toml");
  if (!f) return false;
  auto trim = [](std::string x) {
    const char* ws = " \t\r";
    x.erase(0, x.find_first_not_of(ws));
    x.erase(x.find_last_not_of(ws) + 1);
    return x;
  };
  std::string line, table, declared, family;
  int mentions = 0;
  bool batch = false;
  while (std::getline(f, line)) {
    line = trim(line);
    if (line.empty() || line[0] == '#') continue;
    if (line.find("requires_message_ledger") != std::string::npos) mentions++;
    if (line[0] == '[') { table = line; batch |= line == "[batch]"; continue; }
    const size_t eq = line.find('=');
    if (eq == std::string::npos) continue;
    const std::string key = trim(line.substr(0, eq));
    std::string v = line.substr(eq + 1);
    if (table == "[scoring.params]" && key == "requires_message_ledger") {
      const size_t hash = v.find('#');
      declared = trim(hash == std::string::npos ? v : v.substr(0, hash));
    } else if (table == "[task]" && key == "scenario_family") {
      family = trim(v);
    }
  }
  if (batch) return false;
  if (declared == "false" || declared == "true") return mentions == 1 && declared == "false";
  return mentions == 0 && (family == "\"throughput-scale\"" ||
                           family.rfind("\"throughput-scale\" #", 0) == 0);
}

std::optional<Json> run_scenario(const std::string& config, const std::string& out,
                                 const std::optional<std::string>& seed, bool strict,
                                 bool ledger = true) {
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
  try { result = run_write(std::move(params), trace.string(), ledger ? msg.string() : ""); }
  catch (const std::runtime_error&) { if (strict) throw; return std::nullopt; }
  double written = since(started);
  const std::string& trace_hash = result.trace_hash;  // computed while writing
  const std::string& message_hash = result.message_hash;
  struct rusage usage{}; if (getrusage(RUSAGE_SELF, &usage)) throw std::runtime_error("getrusage failed");
  auto peak = static_cast<int64_t>(usage.ru_maxrss) * 1024;
  Json ev = {{"scenario_id", scenario["scenario_id"]}, {"seed", scenario["seed"]},
    {"n_events", result.events}, {"n_messages", result.messages}, {"engine", "native"},
    {"trace_sha256", trace_hash}, {"peak_memory_bytes", peak},
    {"gpu_seconds", 0.0}, {"simulation_wall_clock_sec", result.seconds}};
  // One events.json write; no profile.json (not part of the output contract): every file
  // operation on the output mount counts toward the run's wall time.
  (void)configured; (void)written;
  ev["wall_clock_sec"] = since(started); ev["events_per_sec"] = result.events / ev["wall_clock_sec"].get<double>();
  if (ledger) ev["message_trace_sha256"] = message_hash;
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
    if (a == "--help" || a == "-h") {
      std::cout << "simulate-batch --batch-dir DIR --out-dir DIR [--trace-mode buffered]\n";
      return 0;
    }
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
  // Sub-scenarios are independent and deterministic (the isolation gate checks each against
  // its isolated reference), so they run concurrently; the aggregate keeps the sorted order.
  auto t0 = Clock::now();
  std::vector<std::optional<Json>> results(names.size());
  std::vector<std::exception_ptr> errors(names.size());
  std::atomic<size_t> next{0};
  auto worker = [&] {
    for (size_t i; (i = next.fetch_add(1)) < names.size();) {
      const std::string sub = names[i].substr(0, names[i].size() - 5);
      const auto sub_out = (std::filesystem::path(out_dir) / sub / "trace.parquet").string();
      try {
        results[i] = run_scenario((std::filesystem::path(batch_dir) / names[i]).string(), sub_out,
                                  std::nullopt, strict);
      } catch (...) {
        errors[i] = std::current_exception();
      }
    }
  };
  {
    const size_t nworkers = std::min<size_t>(3, names.size());
    std::vector<std::thread> pool;
    for (size_t w = 0; w + 1 < nworkers; w++) pool.emplace_back(worker);
    worker();
    for (auto& th : pool) th.join();
  }
  for (size_t i = 0; i < names.size(); i++) {
    if (errors[i] && strict) std::rethrow_exception(errors[i]);
    if (errors[i] || !results[i]) return fallback(argc, argv, true);
    const Json& ev = *results[i];
    total_events += ev["n_events"].get<int64_t>();
    peak_memory = std::max<int64_t>(peak_memory, ev["peak_memory_bytes"].get<int64_t>());
    gpu_seconds += ev["gpu_seconds"].get<double>();
    nlohmann::ordered_json entry;
    entry["sub"] = names[i].substr(0, names[i].size() - 5);
    entry["n_events"] = ev["n_events"];
    entry["trace_sha256"] = ev["trace_sha256"];
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
  std::cout.flush();
  std::fflush(nullptr);
  T3_EXIT(0);
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
    auto ev = run_scenario(config, out, seed, strict, !ledger_optional(config));
    if (!ev) return fallback(argc, argv);
    std::cout << ev->dump() << '\n';
    std::cout.flush();
    std::fflush(nullptr);
    T3_EXIT(0);  // outputs are written and closed; skip teardown of the large in-memory state
  } catch (const std::exception& e) { std::cerr << "simulate: " << e.what() << '\n'; return 1; }
}
