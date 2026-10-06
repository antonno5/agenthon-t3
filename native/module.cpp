// CPython binding: _t3engine.run(cfg: dict) -> dict[str, bytes].
// cfg is built by abides_fork/native.py; the returned buffers are little-endian column
// arrays (see the keys below) that native.py wraps with numpy.frombuffer.
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <stdexcept>
#include <string>

#include "engine.hpp"

namespace {

PyObject* get(PyObject* d, const char* k) {
  PyObject* v = PyDict_GetItemString(d, k);  // borrowed
  if (!v) throw std::runtime_error(std::string("missing cfg key: ") + k);
  return v;
}
int64_t get_i(PyObject* d, const char* k) {
  const long long v = PyLong_AsLongLong(get(d, k));
  if (PyErr_Occurred()) throw std::runtime_error(std::string("bad int cfg key: ") + k);
  return v;
}
double get_f(PyObject* d, const char* k) {
  PyObject* o = get(d, k);
  if (!PyFloat_CheckExact(o)) throw std::runtime_error(std::string("cfg key must be float: ") + k);
  return PyFloat_AS_DOUBLE(o);
}
int64_t item_i(PyObject* seq, Py_ssize_t i) {
  const long long v = PyLong_AsLongLong(PyTuple_GET_ITEM(seq, i));
  if (PyErr_Occurred()) throw std::runtime_error("bad int in tuple");
  return v;
}
double item_f(PyObject* seq, Py_ssize_t i) {
  PyObject* o = PyTuple_GET_ITEM(seq, i);
  if (!PyFloat_CheckExact(o)) throw std::runtime_error("expected float in tuple");
  return PyFloat_AS_DOUBLE(o);
}

t3::Params parse(PyObject* cfg) {
  if (!PyDict_Check(cfg)) throw std::runtime_error("cfg must be a dict");
  t3::Params p;
  const int64_t seed = get_i(cfg, "seed");
  if (seed < 0 || seed > 0xFFFFFFFFLL) throw std::runtime_error("seed out of range");
  p.seed = static_cast<uint32_t>(seed);
  p.start_time = get_i(cfg, "start_time");
  p.mkt_open = get_i(cfg, "mkt_open");
  p.mkt_close = get_i(cfg, "mkt_close");
  p.stop_time = get_i(cfg, "stop_time");
  p.oracle_close = get_i(cfg, "oracle_close");
  p.default_delay = get_i(cfg, "default_delay");
  p.r_bar = get_i(cfg, "r_bar");
  p.kappa = get_f(cfg, "kappa");
  p.fund_vol = get_f(cfg, "fund_vol");
  p.megashock_lambda_a = get_f(cfg, "megashock_lambda_a");
  p.megashock_mean = get_f(cfg, "megashock_mean");
  p.megashock_var = get_f(cfg, "megashock_var");
  PyObject* jumps = get(cfg, "jumps");
  if (!PyList_Check(jumps)) throw std::runtime_error("jumps must be a list");
  for (Py_ssize_t i = 0; i < PyList_GET_SIZE(jumps); i++) {
    PyObject* j = PyList_GET_ITEM(jumps, i);
    if (!PyTuple_Check(j) || PyTuple_GET_SIZE(j) != 2) throw std::runtime_error("bad jump");
    p.jumps.push_back(t3::Jump{item_i(j, 0), item_i(j, 1), false});
  }
  p.pipeline_delay = get_i(cfg, "pipeline_delay");
  p.computation_delay = get_i(cfg, "computation_delay");
  p.stp = static_cast<int>(get_i(cfg, "stp"));
  p.lat_model = static_cast<int>(get_i(cfg, "lat_model"));
  p.lat_mu = get_f(cfg, "lat_mu");
  p.lat_sigma = get_f(cfg, "lat_sigma");
  p.lat_min = get_f(cfg, "lat_min");
  p.lat_max = get_f(cfg, "lat_max");
  p.lat_alpha = get_f(cfg, "lat_alpha");
  p.lat_mean = get_f(cfg, "lat_mean");
  PyObject* agents = get(cfg, "agents");
  if (!PyList_Check(agents)) throw std::runtime_error("agents must be a list");
  for (Py_ssize_t i = 0; i < PyList_GET_SIZE(agents); i++) {
    PyObject* a = PyList_GET_ITEM(agents, i);
    if (!PyTuple_Check(a) || PyTuple_GET_SIZE(a) != 8) throw std::runtime_error("bad agent");
    t3::AgentParams ap;
    ap.kind = static_cast<int>(item_i(a, 0));
    ap.interval = item_i(a, 1);
    ap.d0 = item_f(a, 2);
    ap.d1 = item_f(a, 3);
    ap.i0 = item_i(a, 4);
    ap.i1 = item_i(a, 5);
    ap.i2 = item_i(a, 6);
    ap.i3 = item_i(a, 7);
    p.agents.push_back(ap);
  }
  return p;
}

template <class T>
int put(PyObject* out, const char* key, const std::vector<T>& v) {
  PyObject* b = PyBytes_FromStringAndSize(reinterpret_cast<const char*>(v.data()),
                                          static_cast<Py_ssize_t>(v.size() * sizeof(T)));
  if (!b) return -1;
  const int rc = PyDict_SetItemString(out, key, b);
  Py_DECREF(b);
  return rc;
}

// Arrow utf8 layout for a code column: int32 offsets (n + 1) + concatenated bytes.
int put_strings(PyObject* out, const char* key, const std::vector<uint8_t>& codes,
                const char* const* names) {
  std::vector<int32_t> offsets(codes.size() + 1);
  std::string data;
  offsets[0] = 0;
  for (size_t i = 0; i < codes.size(); i++) {
    data += names[codes[i]];
    offsets[i + 1] = static_cast<int32_t>(data.size());
  }
  std::string ko = std::string(key) + "_offsets", kd = std::string(key) + "_data";
  if (put(out, ko.c_str(), offsets)) return -1;
  std::vector<char> d(data.begin(), data.end());
  return put(out, kd.c_str(), d);
}

// Arrow validity bitmap (LSB first, 1 = valid) from per-row null flags.
int put_validity(PyObject* out, const char* key, const std::vector<uint8_t>& nulls) {
  std::vector<uint8_t> bm((nulls.size() + 7) / 8, 0);
  int64_t null_count = 0;
  for (size_t i = 0; i < nulls.size(); i++) {
    if (nulls[i])
      null_count++;
    else
      bm[i >> 3] |= static_cast<uint8_t>(1u << (i & 7));
  }
  if (put(out, key, bm)) return -1;
  std::string kc = std::string(key) + "_count";
  PyObject* c = PyLong_FromLongLong(null_count);
  if (!c) return -1;
  const int rc = PyDict_SetItemString(out, kc.c_str(), c);
  Py_DECREF(c);
  return rc;
}

std::vector<int64_t> iota64(size_t n) {
  std::vector<int64_t> v(n);
  for (size_t i = 0; i < n; i++) v[i] = static_cast<int64_t>(i);
  return v;
}

const char* const kTraceMsgTypes[] = {"ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED",
                                      "PARTIAL_FILL",    "ORDER_FILLED",   "QUOTE_UPDATE"};
const char* const kSides[] = {"BID", "ASK"};

PyObject* py_run(PyObject*, PyObject* cfg) {
  t3::Params params;
  try {
    params = parse(cfg);
  } catch (const std::exception& e) {
    if (!PyErr_Occurred()) PyErr_SetString(PyExc_ValueError, e.what());
    return nullptr;
  }
  t3::Result r;
  try {
    r = t3::run(std::move(params));
  } catch (const std::exception& e) {
    PyErr_SetString(PyExc_RuntimeError, e.what());
    return nullptr;
  }
  PyObject* out = PyDict_New();
  if (!out) return nullptr;
  const t3::TraceColumns& t = r.trace;
  const t3::MessageColumns& m = r.messages;
  if (put(out, "t_ns", t.t_ns) || put(out, "agent_id", t.agent_id) ||
      put(out, "msg_type", t.msg_type) || put(out, "side", t.side) ||
      put(out, "price", t.price) || put(out, "size", t.size) ||
      put(out, "order_id", t.order_id) || put(out, "m_t_recv", m.t_recv) ||
      put(out, "m_t_send", m.t_send) || put(out, "m_t_send_null", m.t_send_null) ||
      put(out, "m_latency", m.latency) || put(out, "m_src", m.src) ||
      put(out, "m_dst", m.dst) || put(out, "m_message_id", m.message_id) ||
      put(out, "m_msg_type", m.msg_type) || put(out, "m_order_id", m.order_id) ||
      put(out, "m_order_id_null", m.order_id_null) ||
      put(out, "m_causal", m.causal_parent) || put(out, "m_causal_null", m.causal_null) ||
      put(out, "m_seq", iota64(m.t_recv.size())) ||
      put_strings(out, "msg_type_s", t.msg_type, kTraceMsgTypes) ||
      put_strings(out, "side_s", t.side, kSides) ||
      put_strings(out, "m_msg_type_s", m.msg_type, t3::kMsgTypeNames) ||
      put_validity(out, "m_t_send_valid", m.t_send_null) ||
      put_validity(out, "m_order_id_valid", m.order_id_null) ||
      put_validity(out, "m_causal_valid", m.causal_null)) {
    Py_DECREF(out);
    return nullptr;
  }
  return out;
}

PyObject* msg_type_names(PyObject*, PyObject*) {
  PyObject* t = PyTuple_New(t3::MT_COUNT);
  if (!t) return nullptr;
  for (int i = 0; i < t3::MT_COUNT; i++)
    PyTuple_SET_ITEM(t, i, PyUnicode_FromString(t3::kMsgTypeNames[i]));
  return t;
}

PyMethodDef methods[] = {
    {"run", py_run, METH_O, "Run one scenario natively; returns column buffers."},
    {"msg_type_names", msg_type_names, METH_NOARGS, "Ledger msg_type names by code."},
    {nullptr, nullptr, 0, nullptr},
};

PyModuleDef module = {PyModuleDef_HEAD_INIT, "_t3engine", nullptr, -1, methods};

}  // namespace

PyMODINIT_FUNC PyInit__t3engine(void) { return PyModule_Create(&module); }
