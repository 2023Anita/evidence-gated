"""严格合同和不可由任务降级的注册策略。"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from .common import GateError, read_json, safe_path
from .schema_validation import validate


def validate_contract(root: Path, trusted: Path):
    value = read_json(safe_path(root, "task-contract.json"))
    schema = read_json(trusted / "workflow/schemas/task-contract.schema.json")
    validate(value, schema)
    policy = read_json(trusted / "workflow/policies/software-python.json")
    if value["profile"] != policy["profile"]:
        raise GateError(10, "POLICY_DENIED：未注册的 profile")
    if value["risk"]["declared_level"] != "low":
        raise GateError(13, "APPROVAL_REQUIRED：MVP 仅支持低风险纯函数 profile；高风险任务需独立设计")
    if not set(value["scope"]["allowed_paths"]).issubset(policy["required_files"]):
        raise GateError(10, "POLICY_DENIED：此 profile 只允许重试参数函数和对应测试文件")
    minimum_forbidden = {"read_credentials", "upload_private_data", "deploy", "merge_pull_request"}
    if not minimum_forbidden.issubset(value["operations"]["forbidden"]):
        raise GateError(10, "POLICY_DENIED：不得减少项目最低禁止操作")
    for pattern in value["scope"]["allowed_paths"] + value["scope"]["forbidden_paths"]:
        if pattern.startswith("/") or ".." in pattern.split("/") or "\\" in pattern:
            raise GateError(2, "INVALID_CONTRACT：路径模式不得逃逸或使用反斜杠")
    if not set(value["required_evidence"]).issubset(policy["required_evidence"]):
        raise GateError(2, "INVALID_CONTRACT：包含当前 profile 未实现的证据类型")
    for item in value["acceptance"]:
        if item["verifier"] not in policy["verifiers"]:
            raise GateError(2, f"INVALID_CONTRACT：未注册验证器 {item['verifier']}")
    if len({item["id"] for item in value["acceptance"]}) != len(value["acceptance"]):
        raise GateError(2, "INVALID_CONTRACT：重复验收 ID")
    for path in policy["required_files"]:
        safe_path(root, path)
    return value, policy


def metadata_paths(task_id: str) -> set[str]:
    return {"task-contract.json"} | {
        f"tasks/{task_id}/{name}" for name in
        ("spec.md", "plan.md", "baseline.json", "approval-request.json", "approval-request.json.sig")
    }


def check_scope(before: dict, after: dict, contract: dict, policy: dict):
    changed = sorted(path for path in before.keys() | after.keys() if before.get(path) != after.get(path))
    if changed and "edit_allowed_paths" not in contract["operations"]["allowed"]:
        raise GateError(10, "POLICY_DENIED：合同没有允许修改文件")
    forbidden = policy["protected_paths"] + contract["scope"]["forbidden_paths"]
    denied = []
    for path in changed:
        if (any(fnmatch.fnmatchcase(path, rule) for rule in forbidden)
                or not any(fnmatch.fnmatchcase(path, rule) for rule in contract["scope"]["allowed_paths"])):
            denied.append(path)
    if denied:
        raise GateError(10, "POLICY_DENIED：变更超出合同或触及治理文件：" + ", ".join(denied[:10]))
    return changed
