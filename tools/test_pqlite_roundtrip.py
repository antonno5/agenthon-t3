"""Build native/tests/pqlite_roundtrip.cpp and check pyarrow decodes exactly the written values.
usage: test_pqlite_roundtrip.py REPO_DIR"""
import json, pathlib, subprocess, sys, tempfile
import pyarrow.parquet as pq
repo = pathlib.Path(sys.argv[1]); exe = pathlib.Path(tempfile.mkdtemp(dir="/tmp/claude-1001")) / "rt"
subprocess.run(["g++", "-std=c++17", "-O2", "-pthread", f"-I{repo/'native'}", str(repo/"native/tests/pqlite_roundtrip.cpp"), str(repo/"native/pqlite.cpp"), "-o", str(exe)], check=True)
T = ["ORDER_SUBMITTED", "ORDER_ACCEPTED", "ORDER_CANCELLED", "PARTIAL_FILL", "ORDER_FILLED", "QUOTE_UPDATE"]
M = ["AGENT_WAKEUP","MarketClosePriceRequestMsg","MarketHoursRequestMsg","MarketHoursMsg","QuerySpreadMsg","QuerySpreadResponseMsg","LimitOrderMsg","CancelOrderMsg","OrderAcceptedMsg","OrderExecutedMsg","OrderCancelledMsg","MarketClosedMsg","MarketClosePriceMsg"]
bad = 0; runs = 0
for n in [1, 2, 3, 31, 32, 33, 127, 128, 129, 130, 255, 256, 257, 1000, 65535, 65536, 65537, 200001]:
    for seed in range(2):
        d = pathlib.Path(tempfile.mkdtemp(dir="/tmp/claude-1001"))
        subprocess.run([str(exe), str(n), str(seed * 1000 + n), str(d)], check=True)
        raw = json.loads((d / "raw.json").read_text())
        t = pq.read_table(d / "trace.parquet").to_pydict(); m = pq.read_table(d / "message_trace.parquet").to_pydict(); r = raw["trace"]; rm = raw["msg"]
        ok = (t["t_ns"] == r["t_ns"] and t["agent_id"] == r["agent_id"] and t["price"] == r["price"] and t["size"] == r["size"] and t["order_id"] == r["order_id"]
              and t["msg_type"] == [T[i] for i in r["msg_type"]] and t["side"] == [["BID", "ASK"][i] for i in r["side"]]
              and m["seq"] == list(range(n)) and m["t_recv_ns"] == rm["t_recv"] and m["t_send_ns"] == rm["t_send"] and m["latency_ns"] == rm["latency"]
              and m["src_id"] == rm["src"] and m["dst_id"] == rm["dst"] and m["message_id"] == rm["message_id"] and m["msg_type"] == [M[i] for i in rm["msg_type"]]
              and m["order_id"] == rm["order_id"] and m["causal_parent"] == rm["causal"])
        runs += 1; bad += not ok
        if not ok: print("MISMATCH n", n, "seed", seed)
        subprocess.run(["rm", "-rf", str(d)])
print(f"round-trips {runs}  mismatches {bad}"); sys.exit(1 if bad else 0)
