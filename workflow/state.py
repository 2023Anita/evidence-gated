"""状态仅用于本地恢复；每个门禁仍重新计算证据。"""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .common import GateError, canonical, read_json, safe_path, write_json

TRANSITIONS = {
    "DRAFT": {"SPECIFIED"},
    "SPECIFIED": {"APPROVED"},
    "APPROVED": {"EXECUTING", "SPECIFIED", "VERIFYING"},
    "EXECUTING": {"VERIFYING", "SPECIFIED"},
    "VERIFYING": {"REVIEWING", "FAILED", "BLOCKED"},
    "REVIEWING": {"VERIFYING", "EXECUTING", "SPECIFIED", "READY_TO_MERGE"},
    "READY_TO_MERGE": {"MERGED", "EXECUTING", "SPECIFIED", "VERIFYING"},
    "FAILED": {"EXECUTING", "SPECIFIED", "VERIFYING"},
    "BLOCKED": {"APPROVED", "SPECIFIED", "VERIFYING"},
    "HUMAN_ESCALATION_REQUIRED": {"SPECIFIED"},
    "MERGED": set(),
}


@contextmanager
def locked(root: Path):
    directory = safe_path(root, ".egw")
    directory.mkdir(exist_ok=True)
    lock = safe_path(root, ".egw/lock")
    with lock.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise GateError(14, "INVALID_TRANSITION：另一个 egw 进程正在操作此任务") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def get_state(root: Path):
    path = safe_path(root, ".egw/state.json")
    if not path.exists():
        return {"state": "DRAFT", "revision": 0, "authority": "local-advisory"}
    value = read_json(path)
    if (not isinstance(value, dict) or value.get("state") not in TRANSITIONS
            or type(value.get("revision")) is not int or value["revision"] < 0):
        raise GateError(2, "INVALID_INPUT：本地状态文件无效")
    return value


def transition(root: Path, target: str, reason: str, **facts):
    old = get_state(root)
    if target != old["state"] and target not in TRANSITIONS[old["state"]]:
        raise GateError(14, f"INVALID_TRANSITION：{old['state']} → {target}")
    event = {"state": target, "previous": old["state"], "revision": old["revision"] + 1,
             "at": datetime.now(timezone.utc).isoformat(), "reason": reason,
             "authority": "local-advisory", **facts}
    # 事件先落盘；进程异常后仍以重新验证恢复，不信任本地事件作为授权。
    path = safe_path(root, ".egw/events.jsonl")
    with path.open("ab") as stream:
        stream.write(canonical(event))
        stream.flush()
    write_json(safe_path(root, ".egw/state.json"), event)
    return event
