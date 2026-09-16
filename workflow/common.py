"""有界文件读取、确定性摘要和原子写入。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

MAX_BYTES = 4 * 1024 * 1024
MAX_FILES = 10000


class GateError(Exception):
    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


def canonical(value) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def safe_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or not path.parts or any(p in ("..", ".") for p in path.parts):
        raise GateError(10, f"POLICY_DENIED：非法相对路径 {relative!r}")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise GateError(10, f"POLICY_DENIED：不接受符号链接 {relative!r}")
    if not current.resolve().is_relative_to(root.resolve()):
        raise GateError(10, "POLICY_DENIED：路径逃逸")
    return current


def read_bytes(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GateError(11, f"EVIDENCE_MISSING：不是普通文件 {path.name}")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise GateError(2, f"INVALID_INPUT：文件超过 {MAX_BYTES} 字节 {path.name}")
    return data


def no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"重复 JSON 字段 {key}")
        result[key] = value
    return result


def read_json(path: Path):
    try:
        return json.loads(read_bytes(path), object_pairs_hook=no_duplicates,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, UnicodeError) as error:
        raise GateError(2, f"INVALID_INPUT：{path.name} JSON 无效：{error}") from error


def atomic_write(path: Path, data: bytes):
    if path.is_symlink():
        raise GateError(10, "POLICY_DENIED：写入目标不能是符号链接")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".egw-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_json(path: Path, value):
    atomic_write(path, canonical(value))


def manifest(root: Path, excluded: set[str] | None = None) -> dict[str, str]:
    """不遵循 .gitignore；未跟踪文件也进入检查，仅跳过固定运行目录。"""
    excluded = excluded or set()
    result = {}
    skipped = {".git", ".egw", ".venv", "__pycache__"}
    for directory, dirs, files in os.walk(root, followlinks=False):
        parent = Path(directory)
        for name in dirs + files:
            item = parent / name
            if item.is_symlink():
                raise GateError(10, f"POLICY_DENIED：候选树含符号链接 {item.relative_to(root)}")
        dirs[:] = sorted(d for d in dirs if d not in skipped)
        for name in sorted(files):
            path = parent / name
            relative = path.relative_to(root).as_posix()
            if relative in excluded or relative == ".git":
                continue
            result[relative] = hashlib.sha256(read_bytes(path)).hexdigest()
            if len(result) > MAX_FILES:
                raise GateError(2, "INVALID_INPUT：文件数量超过 MVP 限制")
    return result
