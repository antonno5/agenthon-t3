"""Execute the real pinned Kernel with legacy and optimized ledger patches.

No network or Docker calls: supply the unpatched kernel.py from ABIDES commit
f9cbe51342b7dedd9587e4e069040d68a5c6477f. The fixture verifies its SHA-256, applies
the real patches in temporary directories, and executes their Kernel classes.
Only agents, message payloads, latency and summary-file writing are stand-ins.

QFB2_ABIDES_KERNEL_SOURCE=/path/to/kernel.py python -m pytest \
    tests/integration/test_delivery_ledger_kernel.py -m integration
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import io
import logging
import os
import queue
import subprocess
import sys
import types
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.integration
REPO = Path(__file__).resolve().parents[2]
PINNED_KERNEL_SHA256 = (
    "cd0fdd3800ba7b49da0c82d7343f09942c617b6b4b01df37e1babb964f55239e"
)
EPOCH = 1_612_483_200_000_000_001


class Message:
    counter = 1

    def __init__(self, kind: str = "Query", order: Any = None) -> None:
        self.message_id = Message.counter
        Message.counter += 1
        self.kind = kind
        if order is not None:
            self.order = order

    def type(self) -> str:
        return self.kind

    def __lt__(self, other: Message) -> bool:
        return self.message_id < other.message_id


class WakeupMsg(Message):
    pass


class MessageBatch(Message):
    def __init__(self, messages: list[Message]) -> None:
        super().__init__("Batch")
        self.messages = messages


class Latency:
    def __init__(self, values: list[int] | None = None) -> None:
        self.values = deque(values or [])
        self.calls = 0

    def get_latency(self, sender_id: int, recipient_id: int) -> int:
        self.calls += 1
        return self.values.popleft() if self.values else 0


class Agent:
    def __init__(self, ident: int) -> None:
        self.id = ident
        self.events: list[tuple[Any, ...]] = []
        self.on_wakeup: Callable[[int], Any] = lambda now: None
        self.on_message: Callable[[int, int, Message], Any] = lambda *args: None

    def kernel_initializing(self, kernel: Any) -> None:
        self.kernel = kernel

    def kernel_starting(self, now: int) -> None:
        pass

    def kernel_stopping(self) -> None:
        pass

    def kernel_terminating(self) -> None:
        pass

    def wakeup(self, now: int) -> Any:
        self.events.append(("wakeup", now))
        return self.on_wakeup(now)

    def receive_message(self, now: int, sender: int, message: Message) -> None:
        self.events.append((message.kind, now, sender, message.message_id))
        self.on_message(now, sender, message)


def compile_kernel(source: str) -> Any:
    tree = ast.parse(source)
    kernel = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == "Kernel"
    )
    future = ast.ImportFrom(
        module="__future__", names=[ast.alias(name="annotations")], level=0
    )
    module = ast.fix_missing_locations(
        ast.Module(body=[future, kernel], type_ignores=[])
    )
    namespace = {
        "queue": queue,
        "np": np,
        "pd": pd,
        "os": os,
        "datetime": datetime,
        "logger": logging.getLogger("test-delivery-ledger"),
        "str_to_ns": lambda value: 0,
        "fmt_ts": str,
        "Message": Message,
        "WakeupMsg": WakeupMsg,
        "MessageBatch": MessageBatch,
    }
    exec(compile(module, "<pinned-patched-kernel>", "exec"), namespace)
    return namespace["Kernel"]


@pytest.fixture(scope="module")
def kernels(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    supplied = os.environ.get("QFB2_ABIDES_KERNEL_SOURCE")
    if not supplied:
        pytest.skip(
            "set QFB2_ABIDES_KERNEL_SOURCE to the unpatched pinned ABIDES kernel.py; no source is downloaded by tests"
        )
    source = Path(supplied).read_bytes()
    assert (
        hashlib.sha256(source).hexdigest() == PINNED_KERNEL_SHA256
    ), "ABIDES kernel source differs from the published pin"
    variants = {}
    for name, patch in {
        "legacy": Path(__file__).parent / "fixtures/legacy_kernel_message_ledger.patch",
        "optimized": REPO / "baselines/patches/kernel_message_ledger.patch",
    }.items():
        applied = os.environ.get(f"QFB2_LEDGER_KERNEL_{name.upper()}")
        if applied:
            variants[name] = compile_kernel(Path(applied).read_text())
            continue
        root = tmp_path_factory.mktemp(f"ledger-{name}")
        target = root / "abides-core/abides_core/kernel.py"
        target.parent.mkdir(parents=True)
        target.write_bytes(source)
        subprocess.run(
            ["git", "apply", "--check", str(patch)],
            cwd=root,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "apply", str(patch)], cwd=root, check=True, capture_output=True
        )
        variants[name] = compile_kernel(target.read_text())
    return variants


@pytest.fixture
def adapter(monkeypatch: pytest.MonkeyPatch) -> Any:
    utils = types.ModuleType("abides_core.utils")
    utils.parse_logs_df = lambda state: state["raw"]  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "abides_core", types.ModuleType("abides_core"))
    monkeypatch.setitem(sys.modules, "abides_core.utils", utils)
    spec = importlib.util.spec_from_file_location(
        "_kernel_delivery_trace",
        Path(os.environ["QFB2_LEDGER_ADAPTER"])
        if os.environ.get("QFB2_LEDGER_ADAPTER")
        else REPO / "baselines/abides_fork/trace.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def make_kernel(kernels: dict[str, Any]) -> Callable[..., Any]:
    Message.counter = 1

    def make(
        *,
        variant: str = "optimized",
        delay: int = 0,
        stop: int = 100,
        latency: Latency | None = None,
    ) -> Any:
        kernel = kernels[variant](
            [Agent(i) for i in range(4)],
            start_time=EPOCH,
            stop_time=EPOCH + stop,
            default_computation_delay=delay,
            agent_latency_model=latency or Latency(),
            random_state=np.random.RandomState(42),
        )
        kernel.write_summary_log = lambda: None
        kernel.initialize()
        return kernel

    return make


def finish(kernel: Any, adapter: Any) -> pd.DataFrame:
    kernel.runner()
    state = kernel.terminate()
    assert not kernel._pending_message_metadata
    return adapter.extract_message_trace(state)


def parquet_bytes(frame: pd.DataFrame) -> bytes:
    stream = io.BytesIO()
    frame.to_parquet(stream, compression="snappy", index=False)
    return stream.getvalue()


def test_delivery_order_differs_from_send_order(make_kernel: Any, adapter: Any) -> None:
    kernel = make_kernel()
    slow, fast = Message("Slow"), Message("Fast")
    kernel.send_message(0, 1, slow, delay=9)
    kernel.send_message(0, 1, fast, delay=2)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [fast.message_id, slow.message_id]
    assert frame["seq"].tolist() == [0, 1]
    assert frame["t_recv_ns"].tolist() == [EPOCH + 2, EPOCH + 9]


def test_equal_time_preserves_sender_recipient_and_message_priority(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel()
    messages = [Message() for _ in range(4)]
    for sender, recipient, msg in [
        (2, 1, messages[0]),
        (0, 2, messages[1]),
        (0, 1, messages[3]),
        (0, 1, messages[2]),
    ]:
        kernel.send_message(sender, recipient, msg)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [
        messages[i].message_id for i in [2, 3, 1, 0]
    ]
    assert frame["seq"].tolist() == [0, 1, 2, 3]


def test_requeued_messages_preserve_send_metadata_without_duplicates(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel(delay=10)
    kernel.agent_current_times[1] = EPOCH + 50
    messages = [Message() for _ in range(3)]
    for msg in messages:
        kernel.send_message(0, 1, msg)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [msg.message_id for msg in messages]
    assert frame["t_send_ns"].tolist() == [EPOCH + 10] * 3
    assert frame["t_recv_ns"].tolist() == [EPOCH + 10] * 3
    assert frame["latency_ns"].tolist() == [0] * 3
    assert [event[1] for event in kernel.agents[1].events] == [
        EPOCH + 50,
        EPOCH + 60,
        EPOCH + 70,
    ]
    assert frame["seq"].tolist() == [0, 1, 2]


def test_requeued_wakeups_are_logged_once_at_processing_time(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel(delay=10)
    kernel.agent_current_times[1] = EPOCH + 50
    kernel.set_wakeup(1, EPOCH + 1)
    kernel.set_wakeup(1, EPOCH + 2)
    frame = finish(kernel, adapter)
    assert frame["seq"].tolist() == [0, 1]
    assert frame["t_recv_ns"].tolist() == [EPOCH + 50, EPOCH + 60]
    assert frame["t_send_ns"].isna().all()
    assert frame["causal_parent"].isna().all()
    assert frame["latency_ns"].tolist() == [0, 0]


def test_broadcast_keeps_metadata_for_each_recipient(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel(latency=Latency([9, 2]))
    message = Message("Broadcast")
    kernel.send_message(0, 1, message)
    kernel.send_message(0, 2, message)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [message.message_id] * 2
    assert frame["dst_id"].tolist() == [2, 1]
    assert frame["latency_ns"].tolist() == [2, 9]


def test_batch_logs_submessages_and_draws_latency_once(
    make_kernel: Any, adapter: Any
) -> None:
    latency = Latency([7])
    kernel = make_kernel(delay=3, latency=latency)
    messages = [Message("First"), Message("Second"), Message("Third")]
    batch = MessageBatch(messages)
    kernel.send_message(0, 1, batch)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [msg.message_id for msg in messages]
    assert batch.message_id not in frame["message_id"].tolist()
    assert frame["seq"].tolist() == [0, 1, 2]
    assert frame["t_send_ns"].tolist() == [EPOCH + 3] * 3
    assert frame["t_recv_ns"].tolist() == [EPOCH + 10] * 3
    assert frame["latency_ns"].tolist() == [7] * 3
    assert latency.calls == 1


def test_empty_batch_has_no_delivery_rows(make_kernel: Any, adapter: Any) -> None:
    kernel = make_kernel()
    kernel.send_message(0, 1, MessageBatch([]))
    assert finish(kernel, adapter).empty


def test_batch_responses_keep_each_submessage_as_causal_parent(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel()
    requests = [Message("Request"), Message("Request")]
    kernel.agents[1].on_message = lambda now, sender, msg: kernel.send_message(
        1, sender, Message("Reply")
    )
    kernel.send_message(0, 1, MessageBatch(requests))
    frame = finish(kernel, adapter)
    replies = frame[frame["msg_type"] == "Reply"]
    assert replies["causal_parent"].tolist() == [msg.message_id for msg in requests]
    assert frame[frame["msg_type"] == "Request"]["causal_parent"].isna().all()


def test_send_snapshot_survives_payload_mutation(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel()
    order = types.SimpleNamespace(order_id=2**53 + 1)
    message = Message("Before", order)
    kernel.send_message(0, 1, message)
    message.kind = "After"
    order.order_id = 999
    frame = finish(kernel, adapter)
    assert frame["msg_type"].tolist() == ["Before"]
    assert frame["order_id"].tolist() == [2**53 + 1]


def test_pending_send_is_dropped_when_runner_stops(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel(stop=10)
    kernel.set_wakeup(0, EPOCH + 11)
    message = Message("Undelivered")
    kernel.send_message(0, 1, message, delay=50)
    kernel.runner()
    assert (message.message_id, 1) in kernel._pending_message_metadata
    state = kernel.terminate()
    assert not kernel._pending_message_metadata
    frame = adapter.extract_message_trace(state)
    assert frame["msg_type"].tolist() == ["AGENT_WAKEUP"]


@pytest.mark.parametrize("offset", [10, 11])
def test_stop_boundary_preserves_upstream_pop_behavior(
    make_kernel: Any, adapter: Any, offset: int
) -> None:
    # Upstream checks the previous current_time before popping, and may deliver
    # the first event after stop_time. Instrumentation must preserve this behavior.
    kernel = make_kernel(stop=10)
    message = Message()
    kernel.send_message(0, 1, message, delay=offset)
    frame = finish(kernel, adapter)
    assert frame["message_id"].tolist() == [message.message_id]
    assert frame["t_recv_ns"].tolist() == [EPOCH + offset]


def test_runner_pause_keeps_pending_metadata_and_contiguous_seq(
    make_kernel: Any, adapter: Any
) -> None:
    kernel = make_kernel()
    message = Message()
    kernel.send_message(0, 1, message, delay=10)
    kernel.agents[2].on_wakeup = lambda now: {"pause": True}
    kernel.set_wakeup(2, EPOCH + 1)
    result = kernel.runner()
    assert result["done"] is False
    assert (message.message_id, 1) in kernel._pending_message_metadata
    frame = finish(kernel, adapter)
    assert frame["seq"].tolist() == [0, 1]
    assert frame["msg_type"].tolist() == ["AGENT_WAKEUP", "Query"]


def test_market_instances_have_independent_ledgers(
    make_kernel: Any, adapter: Any
) -> None:
    first, second = make_kernel(), make_kernel()
    first.send_message(0, 1, Message("FirstMarket"))
    second.send_message(0, 1, Message("SecondMarket"))
    one, two = finish(first, adapter), finish(second, adapter)
    assert one["msg_type"].tolist() == ["FirstMarket"]
    assert two["msg_type"].tolist() == ["SecondMarket"]
    assert one["seq"].tolist() == two["seq"].tolist() == [0]


@pytest.mark.parametrize("seed", range(20))
def test_randomized_scenarios_match_legacy_callbacks_and_parquet(
    make_kernel: Any, adapter: Any, seed: int
) -> None:
    outputs = []
    for variant in ("legacy", "optimized"):
        Message.counter = 1
        rng = np.random.RandomState(seed)
        latency = Latency(rng.randint(0, 30, size=100).tolist())
        kernel = make_kernel(variant=variant, delay=3, stop=80, latency=latency)

        def send_burst(now: int) -> None:
            for _ in range(12):
                recipient = int(rng.randint(1, 4))
                order = types.SimpleNamespace(order_id=2**53 + int(rng.randint(1, 100)))
                messages = [
                    Message("Request", order) for _ in range(int(rng.randint(1, 4)))
                ]
                kernel.send_message(0, recipient, MessageBatch(messages))
            shared = Message("Broadcast")
            kernel.send_message(0, 1, shared)
            kernel.send_message(0, 2, shared)
            kernel.send_message(0, 3, Message("Undelivered"), delay=1000)

        kernel.agents[0].on_wakeup = send_burst
        for agent in kernel.agents[1:]:

            def respond(
                now: int, sender: int, msg: Message, ident: int = agent.id
            ) -> None:
                if msg.kind == "Request":
                    kernel.send_message(ident, sender, Message("Reply", msg.order))

            agent.on_message = respond
        kernel.set_wakeup(0, EPOCH + 1)
        kernel.set_wakeup(1, EPOCH + 2)
        kernel.set_wakeup(2, EPOCH + 81)
        kernel.runner()
        state = kernel.terminate()
        frame = adapter.extract_message_trace(state)
        outputs.append(
            (frame, [agent.events for agent in kernel.agents], latency.calls)
        )
    pd.testing.assert_frame_equal(outputs[0][0], outputs[1][0])
    assert outputs[0][1:] == outputs[1][1:]
    assert parquet_bytes(outputs[0][0]) == parquet_bytes(outputs[1][0])
