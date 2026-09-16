"""只读平台裁决；未配置可信生产者时一律拒绝提升状态。"""

from __future__ import annotations

import json
import re
import subprocess

from .common import GateError, read_json
from .git_context import git, local_head
from .state import get_state, transition


def gh_json(*args):
    try:
        result = subprocess.run(["gh", *args], capture_output=True, timeout=30)
        if result.returncode:
            raise GateError(20, "INFRA_ERROR：GitHub 查询失败或未认证")
        return json.loads(result.stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise GateError(20, "INFRA_ERROR：无法获得有效平台响应") from error


def merge_gate(engine, pr):
    policy = read_json(engine.trusted / "workflow/policies/github.json")
    if policy.get("mode") != "protected-workflow":
        raise GateError(20, "INFRA_ERROR：平台门禁未配置；需维护者先保护 Workflow、Required Check 和审批规则")
    repository = policy.get("repository")
    if not isinstance(repository, str) or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise GateError(20, "INFRA_ERROR：受信任仓库配置无效")
    if not pr or pr < 1:
        raise GateError(2, "INVALID_INPUT：merge 检查需要 --pr 正整数")
    engine.approved()
    head = local_head(engine.root)
    if not head or git(engine.root, "status", "--porcelain", "--untracked-files=normal").strip():
        raise GateError(11, "EVIDENCE_STALE：平台检查需要项目独立 Git 仓库且工作树干净")
    data = gh_json("pr", "view", str(pr), "--repo", repository, "--json",
                   "headRefOid,baseRefName,mergeStateStatus,reviewDecision,mergedAt,isDraft,url")
    if data.get("headRefOid") != head or data.get("baseRefName") != policy["base_branch"]:
        raise GateError(11, "EVIDENCE_STALE：当前提交或目标分支与 PR 不一致")
    if data.get("mergedAt"):
        # 平台已经合并的事实不依赖本地缓存是否经历 READY_TO_MERGE。
        return {"state": "MERGED", "authority": "github", "url": data["url"],
                "merged_at": data["mergedAt"], "authorizes_merge": False}
    if data.get("isDraft") or data.get("reviewDecision") != "APPROVED":
        raise GateError(13, "APPROVAL_REQUIRED：当前 PR 尚未获得平台审查批准")
    if data.get("mergeStateStatus") != "CLEAN":
        raise GateError(11, "EVIDENCE_STALE：GitHub 尚未确认当前 PR 可合并")
    runs = gh_json("api", f"repos/{repository}/actions/runs?head_sha={head}&event=pull_request&per_page=100")
    relevant = [r for r in runs.get("workflow_runs", []) if r.get("path") == policy["workflow_path"]]
    if not relevant:
        raise GateError(11, "EVIDENCE_MISSING：没有指定可信工作流对应的运行")
    latest = max(relevant, key=lambda r: (r["run_number"], r["run_attempt"]))
    if latest.get("head_sha") != head or latest.get("status") != "completed" or latest.get("conclusion") != "success":
        raise GateError(12, "CHECK_FAILED：指定工作流最新运行未通过")
    jobs = gh_json("api", f"repos/{repository}/actions/runs/{latest['id']}/attempts/{latest['run_attempt']}/jobs?per_page=100")
    matches = [j for j in jobs.get("jobs", []) if j.get("name") == policy["required_check"]]
    if len(matches) != 1 or matches[0].get("conclusion") != "success":
        raise GateError(12, "CHECK_FAILED：缺少唯一通过的 evidence-gate job")
    # 避免请求期间新推送导致接受旧 head。
    fresh = gh_json("pr", "view", str(pr), "--repo", repository, "--json", "headRefOid,mergeStateStatus,reviewDecision")
    if fresh.get("headRefOid") != head or fresh.get("mergeStateStatus") != "CLEAN" or fresh.get("reviewDecision") != "APPROVED":
        raise GateError(11, "EVIDENCE_STALE：查询期间 PR 状态变化")
    if get_state(engine.root)["state"] == "REVIEWING":
        transition(engine.root, "READY_TO_MERGE", "平台当前版本检查和人工审批通过")
    return {"state": "READY_TO_MERGE", "authority": "github-read-only", "head_sha": head,
            "run_id": latest["id"], "authorizes_merge": False,
            "message": "当前平台条件满足；本命令不执行或授权合并，实际合并时平台会再次裁决。"}
