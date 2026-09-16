#!/usr/bin/env python3
"""仅演示随包示例；测试私钥只存在临时目录，不批准任何用户任务。"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from workflow.common import GateError, write_json
from workflow.engine import Engine


def main():
    parser = argparse.ArgumentParser(description="仅运行内置、可信的本地非沙箱演示")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/demo-result.json")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="egw-demo-") as temporary:
        directory = Path(temporary)
        project = directory / "subject"
        trusted = directory / "trusted"
        shutil.copytree(ROOT / "examples/software-retry", project, ignore=shutil.ignore_patterns("__pycache__"))
        for name in ("workflow", "verifiers"):
            shutil.copytree(ROOT / name, trusted / name, ignore=shutil.ignore_patterns("__pycache__"))
        key = directory / "fixture-only-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True, capture_output=True)
        (trusted / "workflow/policies/allowed_signers").write_text("maintainer " + key.with_suffix(".pub").read_text())
        source = project / "src/retry_config.py"
        correct = source.read_text()
        source.write_text(correct.replace("type(value) is not int", "not isinstance(value, int)"))
        engine = Engine(project, trusted)
        engine.init("DEMO-001", "拒绝布尔值作为重试次数，并保留非负整数")
        engine.spec()
        request = project / "tasks/DEMO-001/approval-request.json"
        signature = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(key), "-n", "egw-spec-v1"],
                                   input=request.read_bytes(), capture_output=True, check=True)
        request.with_name(request.name + ".sig").write_bytes(signature.stdout)
        engine.execute()
        try:
            engine.verify(local=True)
            raise AssertionError("错误实现未被拒绝")
        except GateError as error:
            if error.code != 12:
                raise
            failure = {"exit_code": error.code, "reason": str(error)}
        source.write_text(correct)
        engine.execute()
        passed = engine.verify(local=True)
        result = {"demo": "bug-then-fix", "simulated_approval": True,
                  "approval_is_for_fixture_only": True, "private_key_retained": False,
                  "execution": "local-process-not-sandboxed", "before": failure, "after": passed,
                  "github_gate_verified": False, "docker_verified": False}
    write_json(args.output, result)
    print(json.dumps({"demo": "PASS", "before_exit": 12, "after_verdict": "PASS",
                      "report": str(args.output.resolve()), "simulated_approval": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
