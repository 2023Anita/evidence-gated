import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import validate

from workflow.common import GateError, canonical, read_json, write_json
from workflow.engine import Engine
from workflow.state import get_state, locked, transition

ROOT = Path(__file__).resolve().parents[1]


class EngineTests(unittest.TestCase):
    """仅使用临时测试签名身份；不读取真实批准者密钥。"""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="egw-test-")
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.project = self.directory / "project"
        shutil.copytree(ROOT / "examples/software-retry", self.project, ignore=shutil.ignore_patterns("__pycache__"))
        self.trusted = self.directory / "trusted"
        for name in ("workflow", "verifiers"):
            shutil.copytree(ROOT / name, self.trusted / name, ignore=shutil.ignore_patterns("__pycache__"))
        self.key = self.directory / "test-only-key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)], check=True, capture_output=True)
        (self.trusted / "workflow/policies/allowed_signers").write_text("maintainer " + self.key.with_suffix(".pub").read_text())
        self.engine = Engine(self.project, self.trusted)
        self.engine.init("TASK-001", "校验纯函数重试次数的输入边界")
        self.engine.spec()

    def sign(self):
        request = self.project / "tasks/TASK-001/approval-request.json"
        result = subprocess.run(["ssh-keygen", "-Y", "sign", "-f", str(self.key), "-n", "egw-spec-v1"],
                                input=request.read_bytes(), capture_output=True, check=True)
        request.with_name(request.name + ".sig").write_bytes(result.stdout)

    def denied(self, code, operation):
        with self.assertRaises(GateError) as context:
            operation()
        self.assertEqual(context.exception.code, code, str(context.exception))

    def test_default_approval_is_denied(self):
        self.denied(13, self.engine.execute)

    def test_signed_successful_real_task(self):
        self.sign()
        self.engine.execute()
        report = self.engine.verify(local=True)
        self.assertEqual(report["verdict"], "PASS")
        self.assertEqual([c["id"] for c in report["checks"]], ["contract-validation", "scope-diff", "trusted-acceptance-tests", "project-tests"])
        self.assertEqual(report["checks"][2]["tests_run"], 6)
        self.assertEqual(report["checks"][3]["tests_run"], 4)
        self.assertFalse(report["authorizes_merge"])
        validate(report, read_json(ROOT / "workflow/schemas/evidence.schema.json"))
        self.assertEqual(report["producer"], "local")
        self.assertEqual(get_state(self.project)["state"], "REVIEWING")

    def test_actual_bool_bug_is_detected(self):
        self.sign()
        path = self.project / "src/retry_config.py"
        path.write_text(path.read_text().replace("type(value) is not int", "not isinstance(value, int)"))
        self.denied(12, lambda: self.engine.verify(local=True))
        report = read_json(self.project / ".egw/reports/local.json")
        self.assertEqual(report["verdict"], "FAIL")
        self.assertEqual(get_state(self.project)["state"], "FAILED")

    def test_unsigned_plan_change_rejected(self):
        self.sign()
        (self.project / "tasks/TASK-001/plan.md").write_text("计划发生重要变更：增加新的边界与执行步骤。")
        self.denied(13, self.engine.execute)

    def test_contract_downgrade_rejected(self):
        contract = read_json(self.project / "task-contract.json")
        contract["completion"]["allow_skipped_checks"] = True
        write_json(self.project / "task-contract.json", contract)
        self.denied(2, self.engine.spec)

    def test_unknown_verifier_rejected(self):
        contract = read_json(self.project / "task-contract.json")
        contract["acceptance"][0]["verifier"] = "echo-success"
        write_json(self.project / "task-contract.json", contract)
        self.denied(2, self.engine.spec)

    def test_protected_path_rejected(self):
        self.sign()
        (self.project / ".github").mkdir()
        (self.project / ".github/attacker.yml").write_text("name: bypass\n")
        self.denied(10, lambda: self.engine.verify(local=True))

    def test_untracked_out_of_scope_file_rejected(self):
        self.sign()
        (self.project / "extra.py").write_text("print('unexpected')\n")
        self.denied(10, lambda: self.engine.verify(local=True))

    def test_deleted_out_of_scope_file_rejected(self):
        # 将额外文件加入已签名基线，再删除，模拟越界删除。
        baseline_path = self.project / "tasks/TASK-001/baseline.json"
        baseline = read_json(baseline_path)
        baseline["files"]["important.txt"] = "a" * 64
        write_json(baseline_path, baseline)
        self.engine.spec()
        self.sign()
        self.denied(10, lambda: self.engine.verify(local=True))

    def test_fake_state_does_not_grant_approval(self):
        write_json(self.project / ".egw/state.json", {"state": "READY_TO_MERGE", "revision": 100})
        self.denied(13, self.engine.execute)

    def test_fake_pass_report_is_not_used(self):
        self.sign()
        path = self.project / "src/retry_config.py"
        path.write_text("def validate_retry_count(value):\n    return value\n")
        write_json(self.project / ".egw/reports/local.json", {"verdict": "PASS"})
        self.denied(12, lambda: self.engine.verify(local=True))

    def test_governance_tampering_invalidates_approval(self):
        self.sign()
        path = self.trusted / "verifiers/software/runner.py"
        path.write_text(path.read_text() + "\n# altered\n")
        self.denied(13, self.engine.execute)

    def test_signature_other_identity_rejected(self):
        self.sign()
        (self.trusted / "workflow/policies/allowed_signers").write_text("other " + self.key.with_suffix(".pub").read_text())
        self.engine.spec()
        self.sign()
        self.denied(13, self.engine.execute)

    def test_unsigned_baseline_change_rejected(self):
        self.sign()
        path = self.project / "tasks/TASK-001/baseline.json"
        write_json(path, {"git_sha": None, "files": {}})
        self.denied(13, self.engine.execute)

    def test_ci_cannot_fall_back_to_local(self):
        self.sign()
        self.denied(10, lambda: self.engine.verify(local=True, ci=True))

    def test_docker_missing_blocks_instead_of_passing(self):
        self.sign()
        with patch("workflow.sandbox.shutil.which", return_value=None):
            self.denied(20, self.engine.verify)
        self.assertEqual(read_json(self.project / ".egw/reports/local.json")["verdict"], "BLOCKED")

    def test_symlink_in_candidate_rejected(self):
        self.sign()
        (self.project / "link").symlink_to(self.key)
        self.denied(10, lambda: self.engine.verify(local=True))

    def test_symlink_report_cannot_write_outside(self):
        self.sign()
        target = self.directory / "unchanged"
        target.write_text("original")
        (self.project / ".egw/reports").mkdir()
        (self.project / ".egw/reports/local.json").symlink_to(target)
        self.denied(10, lambda: self.engine.verify(local=True))
        self.assertEqual(target.read_text(), "original")

    def test_output_cannot_overwrite_code(self):
        self.sign()
        self.denied(10, lambda: self.engine.verify(local=True, output=self.project / "src/retry_config.py"))

    def test_changed_during_verification_rejected(self):
        self.sign()
        def changing(root, trusted, policy, mode, local):
            path = root / "src/retry_config.py"
            path.write_text(path.read_text() + "\n# concurrent change\n")
            return {"id": mode, "result": "PASS", "tests_run": 1}
        with patch("workflow.engine.run_check", side_effect=changing):
            self.denied(11, lambda: self.engine.verify(local=True))

    def test_skipped_project_tests_rejected(self):
        self.sign()
        path = self.project / "tests/test_retry_config.py"
        path.write_text("import unittest\n@unittest.skip('skip')\nclass TestSkip(unittest.TestCase):\n def test_noop(self): pass\n")
        self.denied(12, lambda: self.engine.verify(local=True))

    def test_missing_project_tests_rejected(self):
        self.sign()
        (self.project / "tests/test_retry_config.py").write_text("# no tests\n")
        self.denied(12, lambda: self.engine.verify(local=True))

    def test_minimum_evidence_not_removed(self):
        path = self.project / "task-contract.json"
        contract = read_json(path)
        contract["required_evidence"] = ["contract-validation"]
        write_json(path, contract)
        self.engine.spec()
        self.sign()
        report = self.engine.verify(local=True)
        self.assertEqual(len(report["checks"]), 4)

    def test_lock_rejects_concurrent_writer(self):
        with locked(self.project):
            with self.assertRaises(GateError) as context:
                with locked(self.project):
                    pass
            self.assertEqual(context.exception.code, 14)

    def test_illegal_state_transition_rejected(self):
        self.denied(14, lambda: transition(self.project, "READY_TO_MERGE", "try bypass"))

    def test_duplicate_json_keys_rejected(self):
        path = self.project / "task-contract.json"
        path.write_text('{"task_id":"A","task_id":"B"}')
        self.denied(2, self.engine.spec)

    def test_unknown_field_rejected(self):
        path = self.project / "task-contract.json"
        contract = read_json(path)
        contract["verify_command"] = "echo pass"
        write_json(path, contract)
        self.denied(2, self.engine.spec)

    def test_timeout_is_failure(self):
        path = self.trusted / "workflow/policies/software-python.json"
        policy = read_json(path)
        policy["timeout_seconds"] = 1
        write_json(path, policy)
        self.engine.spec()
        self.sign()
        (self.project / "src/retry_config.py").write_text("import time\ntime.sleep(10)\n")
        self.denied(12, lambda: self.engine.verify(local=True))
        report = read_json(self.project / ".egw/reports/local.json")
        self.assertEqual(report["verdict"], "FAIL")
        validate(report, read_json(ROOT / "workflow/schemas/evidence.schema.json"))

    def test_only_profile_files_enter_execution_tree(self):
        from workflow.sandbox import run_check
        (self.project / ".env").write_text("DUMMY_FIXTURE_NOT_A_SECRET=example\n")
        policy = read_json(self.trusted / "workflow/policies/software-python.json")
        def inspect(subject, trusted, policy, mode, local):
            names = {p.relative_to(subject).as_posix() for p in subject.rglob("*") if p.is_file()}
            self.assertEqual(names, {"src/retry_config.py", "tests/test_retry_config.py"})
            self.assertFalse((subject / ".env").exists())
            self.assertFalse((subject / "tasks").exists())
            return {"result": "PASS"}
        with patch("workflow.sandbox._run_check", side_effect=inspect):
            run_check(self.project, self.trusted, policy, "project-tests", True)


if __name__ == "__main__":
    unittest.main()
