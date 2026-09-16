"""egw CLI 的黑盒回归测试。

这些测试只通过 scripts/egw.py 的公开命令行接口操作临时项目目录；不创建
Git 仓库、不生成审批签名，也不访问网络或真实凭据。
"""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "scripts" / "egw.py"
SAFE_ENV = {
    "PATH": os.defpath,
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
    "PYTHONIOENCODING": "utf-8",
}


class CliBlackBoxTest(unittest.TestCase):
    """验证 CLI 的输入、JSON 输出和拒绝路径。"""

    @staticmethod
    def _run(*args: object) -> subprocess.CompletedProcess[str]:
        command = [sys.executable, "-I", str(CLI), *(str(arg) for arg in args)]
        return subprocess.run(
            command,
            cwd=REPO_ROOT,
            env=SAFE_ENV,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
        )

    @staticmethod
    def _canonical(value: object) -> bytes:
        return (
            json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")

    def _assert_stdout_json(self, result: subprocess.CompletedProcess[str]) -> dict:
        self.assertEqual(
            result.returncode,
            0,
            msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertEqual(result.stderr, "")
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"成功结果不是 JSON：{result.stdout!r} ({error})")
        self.assertIsInstance(value, dict)
        return value

    def _assert_error(
        self, result: subprocess.CompletedProcess[str], code: int
    ) -> dict:
        self.assertEqual(
            result.returncode,
            code,
            msg=f"stdout={result.stdout!r} stderr={result.stderr!r}",
        )
        self.assertEqual(result.stdout, "")
        try:
            value = json.loads(result.stderr)
        except json.JSONDecodeError as error:
            self.fail(f"错误结果不是 JSON：{result.stderr!r} ({error})")
        self.assertIsInstance(value, dict)
        self.assertFalse(value.get("ok"))
        self.assertEqual(value.get("exit_code"), code)
        return value

    @staticmethod
    def _make_project(root: Path) -> None:
        """建立只包含 MVP 允许文件的临时 Python 项目。"""
        (root / "src").mkdir()
        (root / "tests").mkdir()
        (root / "src/retry_config.py").write_text(
            """def validate_retry_count(value):
    if type(value) is not int:
        raise TypeError("retry count must be an integer")
    if value < 0:
        raise ValueError("retry count must be non-negative")
    return value
""",
            encoding="utf-8",
        )
        (root / "tests/test_retry_config.py").write_text(
            """import unittest

from src.retry_config import validate_retry_count


class RetryConfigTest(unittest.TestCase):
    def test_positive(self):
        self.assertEqual(validate_retry_count(3), 3)

    def test_zero(self):
        self.assertEqual(validate_retry_count(0), 0)

    def test_rejects_invalid_inputs(self):
        for value in (True, False, "3", 3.0, None):
            with self.subTest(value=value), self.assertRaises(TypeError):
                validate_retry_count(value)

    def test_rejects_negative(self):
        with self.assertRaises(ValueError):
            validate_retry_count(-1)
""",
            encoding="utf-8",
        )

    def _init(self, root: Path, objective: str = "验证重试次数输入边界") -> dict:
        self._make_project(root)
        result = self._run(
            "init",
            "--root",
            root,
            "--task",
            "TASK-001",
            "--objective",
            objective,
        )
        return self._assert_stdout_json(result)

    def _spec(self, root: Path) -> dict:
        result = self._run("spec", "--root", root)
        return self._assert_stdout_json(result)

    def test_init_emits_json_and_creates_contract(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            payload = self._init(root)

            self.assertEqual(payload["task_id"], "TASK-001")
            self.assertEqual(payload["state"], "DRAFT")
            self.assertEqual(payload["profile"], "software-python-retry")
            contract = json.loads((root / "task-contract.json").read_text(encoding="utf-8"))
            self.assertEqual(contract["task_id"], "TASK-001")
            self.assertEqual(json.loads((root / ".egw/state.json").read_text()), {
                "state": "DRAFT",
                "revision": 0,
                "authority": "local-advisory",
            })

    def test_init_repeat_is_rejected_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            self._init(root)
            original = (root / "task-contract.json").read_bytes()

            result = self._run(
                "init",
                "--root",
                root,
                "--task",
                "TASK-001",
                "--objective",
                "不应覆盖已有任务",
            )
            error = self._assert_error(result, 14)
            self.assertIn("INVALID_TRANSITION", error["message"])
            self.assertEqual((root / "task-contract.json").read_bytes(), original)

    def test_unknown_command_exits_2(self) -> None:
        result = self._run("unknown-command")

        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)

    def test_spec_writes_canonical_approval_request(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            self._init(root)
            payload = self._spec(root)

            request_path = root / "tasks/TASK-001/approval-request.json"
            request = json.loads(request_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "SPECIFIED")
            self.assertEqual(
                Path(payload["approval_request"]).resolve(), request_path.resolve()
            )
            self.assertEqual(request["task_id"], "TASK-001")
            self.assertEqual(request_path.read_bytes(), self._canonical(request))
            self.assertEqual(
                payload["approval_request_sha256"],
                hashlib.sha256(request_path.read_bytes()).hexdigest(),
            )
            self.assertFalse((request_path.parent / "approval-request.json.sig").exists())

    def test_gate_execute_without_signature_exits_13(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            self._init(root)
            self._spec(root)

            result = self._run(
                "gate", "--root", root, "--checkpoint", "execute"
            )
            error = self._assert_error(result, 13)
            self.assertIn("APPROVAL_REQUIRED", error["message"])
            state = json.loads((root / ".egw/state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["state"], "SPECIFIED")

    def test_gate_review_without_signature_exits_13(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            self._init(root)
            self._spec(root)

            result = self._run(
                "gate", "--root", root, "--checkpoint", "review"
            )
            error = self._assert_error(result, 13)
            self.assertIn("APPROVAL_REQUIRED", error["message"])

    def test_gate_merge_requires_platform_configuration_without_network(self) -> None:
        policy = json.loads(
            (REPO_ROOT / "workflow/policies/github.json").read_text(encoding="utf-8")
        )
        self.assertEqual(policy["mode"], "unconfigured")

        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            result = self._run(
                "gate",
                "--root",
                Path(directory),
                "--checkpoint",
                "merge",
                "--pr",
                "1",
            )
            error = self._assert_error(result, 20)
            self.assertIn("平台门禁未配置", error["message"])

    def test_verify_failure_writes_non_pass_report(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            self._init(root)
            self._spec(root)
            report_path = root / ".egw/reports/failed.json"

            result = self._run(
                "verify",
                "--root",
                root,
                "--local",
                "--output",
                report_path,
            )
            error = self._assert_error(result, 13)
            self.assertIn("APPROVAL_REQUIRED", error["message"])
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertIn(report["verdict"], {"BLOCKED", "FAIL"})
            self.assertNotEqual(report["verdict"], "PASS")
            self.assertFalse(report["authorizes_merge"])
            self.assertEqual(report["producer"], "local")

    def test_status_is_read_only_and_does_not_create_egw(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            before = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))

            result = self._run("status", "--root", root, "--json")
            payload = self._assert_stdout_json(result)

            after = sorted(path.relative_to(root).as_posix() for path in root.rglob("*"))
            self.assertEqual(before, after)
            self.assertFalse((root / ".egw").exists())
            self.assertEqual(payload["local"]["state"], "DRAFT")
            self.assertEqual(payload["platform"], "NOT_QUERIED")
            self.assertFalse(payload["authorizes_merge"])

    def test_invalid_task_id_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            result = self._run(
                "init",
                "--root",
                root,
                "--task",
                "task_001",
                "--objective",
                "非法任务 ID",
            )
            error = self._assert_error(result, 2)
            self.assertIn("task ID", error["message"])
            self.assertFalse((root / "task-contract.json").exists())

    def test_ci_and_local_verify_are_mutually_exclusive(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            output = root / ".egw/reports/ci.json"
            result = self._run(
                "verify",
                "--root",
                root,
                "--ci",
                "--local",
                "--output",
                output,
            )
            error = self._assert_error(result, 10)
            self.assertIn("POLICY_DENIED", error["message"])
            self.assertFalse(output.exists())

    def test_symlink_root_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            parent = Path(directory)
            real_root = parent / "real"
            symlink_root = parent / "linked"
            real_root.mkdir()
            symlink_root.symlink_to(real_root, target_is_directory=True)

            result = self._run(
                "init",
                "--root",
                symlink_root,
                "--task",
                "TASK-001",
                "--objective",
                "符号链接根目录应拒绝",
            )
            error = self._assert_error(result, 2)
            self.assertIn("符号链接", error["message"])
            self.assertFalse((real_root / "task-contract.json").exists())

    def test_malformed_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(prefix="egw-cli-") as directory:
            root = Path(directory)
            (root / "task-contract.json").write_text(
                '{"schema_version":"1",', encoding="utf-8"
            )

            result = self._run("spec", "--root", root)
            error = self._assert_error(result, 2)
            self.assertIn("INVALID_INPUT", error["message"])
            self.assertFalse((root / "tasks/TASK-001/approval-request.json").exists())


if __name__ == "__main__":
    unittest.main()
