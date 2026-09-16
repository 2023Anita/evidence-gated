"""只读 Git 快照；CI 显式校验基线、PR head 和合并候选关系。"""

from __future__ import annotations

import hashlib
import re
import subprocess
from pathlib import Path

from .common import GateError, MAX_BYTES, MAX_FILES


def git(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GateError(20, "INFRA_ERROR：无法读取 Git 上下文") from error
    if result.returncode:
        raise GateError(20, "INFRA_ERROR：Git 对象缺失或仓库上下文无效")
    return result.stdout


def local_head(root: Path):
    if not (root / ".git").exists():
        return None
    if Path(git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve() != root:
        return None
    return git(root, "rev-parse", "HEAD").decode().strip()


def tree_manifest(root: Path, sha: str, excluded: set[str]):
    if not re.fullmatch(r"[0-9a-f]{40}", sha):
        raise GateError(2, "INVALID_INPUT：Git SHA 必须为 40 位十六进制")
    entries = git(root, "ls-tree", "-r", "-z", sha).split(b"\0")
    if len(entries) > MAX_FILES + 1:
        raise GateError(2, "INVALID_INPUT：Git 文件数超过限制")
    result = {}
    for entry in filter(None, entries):
        info, raw_path = entry.split(b"\t", 1)
        mode, kind, oid = info.decode().split()
        name = raw_path.decode()
        if mode not in ("100644", "100755") or kind != "blob":
            raise GateError(10, "POLICY_DENIED：CI 不支持符号链接、子模块或特殊对象")
        if name in excluded or set(Path(name).parts) & {".egw", ".venv", "__pycache__"}:
            continue
        size = int(git(root, "cat-file", "-s", oid))
        if size > MAX_BYTES:
            raise GateError(2, "INVALID_INPUT：Git blob 超过文件大小限制")
        result[name] = hashlib.sha256(git(root, "cat-file", "blob", oid)).hexdigest()
    return result


def validate_ci(root: Path, baseline: dict, excluded: set[str], base: str, head: str, candidate: str):
    for sha in (base, head, candidate):
        if not sha or not re.fullmatch(r"[0-9a-f]{40}", sha):
            raise GateError(2, "INVALID_INPUT：CI 必须提供完整 base/head/candidate SHA")
    if local_head(root) != candidate:
        raise GateError(11, "EVIDENCE_STALE：checkout 与 candidate SHA 不符")
    parents = git(root, "show", "-s", "--format=%P", candidate).decode().split()
    if parents != [base, head]:
        raise GateError(11, "EVIDENCE_STALE：此 MVP 仅接受 base/head 对应的双亲 PR 合并候选")
    if baseline["git_sha"] != base or baseline["files"] != tree_manifest(root, base, excluded):
        raise GateError(13, "APPROVAL_REQUIRED：批准的基线与目标分支不一致，需要重新规格与签署")
    return {"base_sha": base, "head_sha": head, "candidate_sha": candidate}
