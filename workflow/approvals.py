"""验证外部审批者的 SSH 签名；不提供签署或伪造审批的命令。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .common import GateError, canonical, read_bytes, read_json


def verify_approval(request: dict, request_path: Path, trusted: Path, identity: str):
    signers = trusted / "workflow/policies/allowed_signers"
    signature = request_path.with_name(request_path.name + ".sig")
    if not signers.is_file() or not signature.is_file():
        raise GateError(13, "APPROVAL_REQUIRED：缺少受信任批准者配置或审批签名；请由人工在独立环境签署")
    if read_json(request_path) != request or read_bytes(request_path) != canonical(request):
        raise GateError(13, "APPROVAL_REQUIRED：审批请求与当前合同、计划或基线不一致，请重新执行 spec 并签署")
    try:
        result = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(signers), "-I", identity,
             "-n", "egw-spec-v1", "-s", str(signature)],
            input=canonical(request), capture_output=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise GateError(20, "INFRA_ERROR：无法运行 SSH 签名验证") from error
    if result.returncode:
        raise GateError(13, "APPROVAL_REQUIRED：签名无效、身份不受信任或批准内容已变化")
    return {"identity": identity, "method": "ssh-signature", "namespace": "egw-spec-v1"}
