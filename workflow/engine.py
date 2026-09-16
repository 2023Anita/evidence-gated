"""合同、签名、范围和执行证据的统一入口。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from .approvals import verify_approval
from .common import GateError, atomic_write, canonical, digest, manifest, read_bytes, read_json, safe_path, write_json
from .contract import check_scope, metadata_paths, validate_contract
from .git_context import local_head, tree_manifest, validate_ci
from .sandbox import run_check
from .state import get_state, transition


class Engine:
    def __init__(self, root: Path, trusted: Path):
        self.input_root = root.absolute()
        self.root = root.resolve()
        self.trusted = trusted.resolve()

    def path(self, relative):
        return safe_path(self.root, relative)

    def init(self, task: str, objective: str):
        if not re.fullmatch(r"[A-Z][A-Z0-9-]{0,63}", task):
            raise GateError(2, "INVALID_CONTRACT：task ID 必须为大写字母、数字和连字符")
        if not objective.strip() or len(objective) > 500:
            raise GateError(2, "INVALID_CONTRACT：目标须为 1–500 个字符")
        if self.path("task-contract.json").exists() or self.path(f"tasks/{task}").exists():
            raise GateError(14, "INVALID_TRANSITION：任务已存在，不覆盖原合同")
        baseline = {"git_sha": local_head(self.root), "files": manifest(self.root)}
        contract = {
            "schema_version": "1", "task_id": task, "profile": "software-python-retry",
            "objective": objective,
            "risk": {"declared_level": "low", "reasons": ["仅限无依赖重试参数纯函数"]},
            "scope": {"allowed_paths": ["src/retry_config.py", "tests/test_retry_config.py"],
                      "forbidden_paths": [".github/**", "workflow/**", "verifiers/**"]},
            "operations": {"allowed": ["read_project_files", "edit_allowed_paths", "run_registered_checks"],
                           "forbidden": ["read_credentials", "upload_private_data", "deploy", "merge_pull_request"]},
            "acceptance": [
                {"id": "AC-001", "statement": "整数 0 和 3 被接受并保留原值", "verifier": "retry-boundaries-v1"},
                {"id": "AC-002", "statement": "负数抛出 ValueError", "verifier": "retry-boundaries-v1"},
                {"id": "AC-003", "statement": "布尔、字符串、浮点数抛出 TypeError", "verifier": "retry-boundaries-v1"}],
            "required_evidence": ["contract-validation", "scope-diff", "trusted-acceptance-tests", "project-tests"],
            "completion": {"all_required_checks": "pass", "allow_missing_evidence": False,
                           "allow_skipped_checks": False, "require_current_revision": True},
            "approvals": {"specification": {"required": True}, "merge": {"required": True}},
            "data": {"classification": "public-code", "external_upload_allowed": False},
        }
        write_json(self.path("task-contract.json"), contract)
        directory = f"tasks/{task}"
        write_json(self.path(f"{directory}/baseline.json"), baseline)
        atomic_write(self.path(f"{directory}/spec.md"),
                     f"# {task} 规格\n\n目标：{objective}\n\n仅修改重试参数校验纯函数及测试。\n"
                     "接受非负整数；负数抛出 ValueError；布尔、浮点、字符串抛出 TypeError。\n"
                     "不涉及网络、依赖、凭据、生产系统或自动提交。\n".encode())
        atomic_write(self.path(f"{directory}/plan.md"),
                     "# 实施计划\n\n1. 阅读当前函数和测试。\n2. 先增加边界测试，再实现类型与取值检查。\n"
                     "3. 运行项目测试和可信验收测试。\n4. 报告证据与限制，交由人工处理外部操作。\n".encode())
        write_json(self.path(".egw/state.json"), {"state": "DRAFT", "revision": 0,
                   "authority": "local-advisory"})
        return {"task_id": task, "state": "DRAFT", "profile": contract["profile"],
                "next": "请检查生成的合同、规格和计划，然后运行 spec。"}

    def load(self):
        return validate_contract(self.root, self.trusted)

    def governance_digest(self):
        files = {}
        for name in ("workflow", "verifiers"):
            files.update({f"{name}/{path}": sha for path, sha in manifest(self.trusted / name).items()})
        return digest(files)

    def request(self, contract, policy):
        directory = f"tasks/{contract['task_id']}"
        baseline = read_json(self.path(f"{directory}/baseline.json"))
        if (not isinstance(baseline, dict) or set(baseline) != {"git_sha", "files"}
                or not isinstance(baseline["files"], dict)
                or not all(isinstance(p, str) and isinstance(s, str) and re.fullmatch(r"[0-9a-f]{64}", s)
                           for p, s in baseline["files"].items())):
            raise GateError(2, "INVALID_INPUT：基线清单无效")
        hashes = {}
        for name in ("spec.md", "plan.md"):
            data = read_bytes(self.path(f"{directory}/{name}"))
            if len(data.strip()) < 20:
                raise GateError(2, f"INVALID_CONTRACT：{name} 过短，缺少可审查内容")
            hashes[name] = hashlib.sha256(data).hexdigest()
        request = {"schema_version": "1", "task_id": contract["task_id"],
                   "contract_sha256": digest(contract), "policy_sha256": digest(policy),
                   "governance_sha256": self.governance_digest(),
                   "baseline_sha256": digest(baseline), "documents": hashes}
        return request, baseline, self.path(f"{directory}/approval-request.json")

    def spec(self):
        contract, policy = self.load()
        request, baseline, path = self.request(contract, policy)
        if get_state(self.root)["state"] == "MERGED":
            raise GateError(14, "INVALID_TRANSITION：已合并任务不能重新规格")
        write_json(path, request)
        transition(self.root, "SPECIFIED", "合同与计划已校验，等待独立签署")
        return {"state": "SPECIFIED", "approval_request": str(path),
                "approval_request_sha256": digest(request), "baseline_git_sha": baseline["git_sha"],
                "next": "请批准者在独立环境审查并签署，不得由 Agent 代签。"}

    def approved(self):
        contract, policy = self.load()
        request, baseline, path = self.request(contract, policy)
        approval = verify_approval(request, path, self.trusted, policy["approval_identity"])
        return contract, policy, request, baseline, approval

    def execute(self):
        contract, policy, request, baseline, approval = self.approved()
        files = manifest(self.root, metadata_paths(contract["task_id"]))
        changed = check_scope(baseline["files"], files, contract, policy)
        current = get_state(self.root)["state"]
        if current in ("SPECIFIED", "BLOCKED"):
            transition(self.root, "APPROVED", "独立签名验证通过", approval=approval)
        transition(self.root, "EXECUTING", "执行前范围检查通过")
        return {"state": "EXECUTING", "authority": "local-advisory", "changed_paths": changed}

    def verify(self, *, local=False, ci=False, output=None, base=None, head=None, candidate=None):
        if ci and local:
            raise GateError(10, "POLICY_DENIED：CI 不允许本地进程后端")
        if output is None:
            destination = self.path(".egw/reports/local.json")
        else:
            supplied = Path(output)
            if not supplied.is_absolute():
                destination = self.path(str(supplied))
            elif supplied.is_relative_to(self.input_root):
                destination = self.path(str(supplied.relative_to(self.input_root)))
            elif supplied.is_relative_to(self.root):
                destination = self.path(str(supplied.relative_to(self.root)))
            else:
                # /var -> /private/var 等系统路径别名不应误判为项目路径攻击。
                if supplied.is_symlink():
                    raise GateError(10, "POLICY_DENIED：报告文件不能是符号链接")
                destination = supplied.parent.resolve() / supplied.name
        # 报告不得覆盖候选业务文件。
        if destination.is_relative_to(self.root) and not destination.is_relative_to(self.root / ".egw"):
            raise GateError(10, "POLICY_DENIED：项目内报告只能写入 .egw/")
        report = {"schema_version": "1", "producer": "ci-context-unattested" if ci else "local",
                  "created_at": datetime.now(timezone.utc).isoformat(), "verdict": "BLOCKED",
                  "authorizes_merge": False, "checks": []}
        started = False
        try:
            contract, policy, request, baseline, approval = self.approved()
            if "run_registered_checks" not in contract["operations"]["allowed"]:
                raise GateError(10, "POLICY_DENIED：合同没有允许执行检查")
            excluded = metadata_paths(contract["task_id"])
            report.update({"task_id": contract["task_id"], "binding": request, "approval": approval})
            if ci:
                report["git"] = validate_ci(self.root, baseline, excluded, base, head, candidate)
                # CI 不能接受 checkout 后产生的未提交候选改动。
                if manifest(self.root, excluded) != tree_manifest(self.root, candidate, excluded):
                    raise GateError(11, "EVIDENCE_STALE：候选工作树与提交不一致")
            before = manifest(self.root)
            source = {p: sha for p, sha in before.items() if p not in excluded}
            changed = check_scope(baseline["files"], source, contract, policy)
            report["subject_sha256"] = digest(before)
            report["changed_paths"] = changed
            report["checks"].extend([{"id": "contract-validation", "result": "PASS"},
                                      {"id": "scope-diff", "result": "PASS"}])
            if not ci:
                state = get_state(self.root)["state"]
                if state == "SPECIFIED":
                    transition(self.root, "APPROVED", "独立签名验证通过")
                transition(self.root, "VERIFYING", "开始重新验证")
                started = True
            for mode in ("trusted-acceptance-tests", "project-tests"):
                report["checks"].append(run_check(self.root, self.trusted, policy, mode, local))
            if manifest(self.root) != before or self.governance_digest() != request["governance_sha256"]:
                raise GateError(11, "EVIDENCE_STALE：验证期间代码或治理文件变化")
            report["verdict"] = "PASS"
            if started:
                transition(self.root, "REVIEWING", "技术验证通过，尚未获得平台合并授权")
            return report
        except GateError as error:
            report.update({"verdict": "FAIL" if error.code in (10, 11, 12) else "BLOCKED",
                           "exit_code": error.code, "reason": str(error)})
            if started:
                transition(self.root, "FAILED" if report["verdict"] == "FAIL" else "BLOCKED", str(error))
            raise
        finally:
            write_json(destination, report)

    def review(self):
        # 不相信本地通过报告；检查 review 时再次运行可信验证。
        return self.verify()

    def status(self):
        state = get_state(self.root)
        result = {"local": state, "platform": "NOT_QUERIED", "authorizes_merge": False,
                  "message": "本地状态不代表平台授权；gate 会重新检查签名和证据。"}
        if self.path("task-contract.json").exists():
            contract, policy = self.load()
            result["task_id"] = contract["task_id"]
            try:
                _, _, _, _, approval = self.approved()
                result["approval"] = approval
            except GateError as error:
                result["approval"] = {"valid": False, "reason": str(error), "exit_code": error.code}
        return result
