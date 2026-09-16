import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from workflow.common import GateError
from workflow.git_context import validate_ci
from workflow.github import merge_gate


class GitBindingTests(unittest.TestCase):
    def test_invalid_sha(self):
        with self.assertRaises(GateError) as context:
            validate_ci(Path("/tmp"), {}, set(), "main", "b" * 40, "c" * 40)
        self.assertEqual(context.exception.code, 2)

    @patch("workflow.git_context.local_head", return_value="c" * 40)
    @patch("workflow.git_context.git", return_value=(("a" * 40) + " " + ("b" * 40)).encode())
    @patch("workflow.git_context.tree_manifest", return_value={"src.py": "a" * 64})
    def test_correct_merge_and_baseline(self, *mocks):
        result = validate_ci(Path("/tmp"), {"git_sha": "a" * 40, "files": {"src.py": "a" * 64}},
                             set(), "a" * 40, "b" * 40, "c" * 40)
        self.assertEqual(result["candidate_sha"], "c" * 40)

    @patch("workflow.git_context.local_head", return_value="d" * 40)
    def test_wrong_checkout(self, *mocks):
        with self.assertRaises(GateError) as context:
            validate_ci(Path("/tmp"), {}, set(), "a" * 40, "b" * 40, "c" * 40)
        self.assertEqual(context.exception.code, 11)

    @patch("workflow.git_context.local_head", return_value="c" * 40)
    @patch("workflow.git_context.git", return_value=(("b" * 40) + " " + ("a" * 40)).encode())
    def test_wrong_merge_parents(self, *mocks):
        with self.assertRaises(GateError) as context:
            validate_ci(Path("/tmp"), {}, set(), "a" * 40, "b" * 40, "c" * 40)
        self.assertEqual(context.exception.code, 11)

    @patch("workflow.git_context.local_head", return_value="c" * 40)
    @patch("workflow.git_context.git", return_value=(("a" * 40) + " " + ("b" * 40)).encode())
    @patch("workflow.git_context.tree_manifest", return_value={"src.py": "b" * 64})
    def test_baseline_tampered(self, *mocks):
        with self.assertRaises(GateError) as context:
            validate_ci(Path("/tmp"), {"git_sha": "a" * 40, "files": {}},
                        set(), "a" * 40, "b" * 40, "c" * 40)
        self.assertEqual(context.exception.code, 13)


class GithubTests(unittest.TestCase):
    def setUp(self):
        self.engine = Mock()
        self.engine.root = Path("/tmp/egw-test")
        self.engine.trusted = Path("/tmp/trusted")
        self.policy = {"mode": "protected-workflow", "repository": "owner/repo", "base_branch": "main",
                       "required_check": "evidence-gate", "workflow_path": ".github/workflows/evidence-gate.yml"}
        self.pr = {"headRefOid": "b" * 40, "baseRefName": "main", "mergeStateStatus": "CLEAN",
                   "reviewDecision": "APPROVED", "mergedAt": None, "isDraft": False, "url": "https://github.com/owner/repo/pull/1"}
        self.run = {"workflow_runs": [{"id": 17, "path": self.policy["workflow_path"], "head_sha": "b" * 40,
                                      "status": "completed", "conclusion": "success", "run_number": 5, "run_attempt": 1}]}
        self.jobs = {"jobs": [{"name": "evidence-gate", "conclusion": "success"}]}

    def invoke(self, responses):
        with patch("workflow.github.read_json", return_value=self.policy), \
             patch("workflow.github.local_head", return_value="b" * 40), \
             patch("workflow.github.git", return_value=b""), \
             patch("workflow.github.get_state", return_value={"state": "SPECIFIED"}), \
             patch("workflow.github.gh_json", side_effect=responses):
            return merge_gate(self.engine, 1)

    def test_unconfigured_fails_closed(self):
        self.policy["mode"] = "unconfigured"
        with self.assertRaises(GateError) as context:
            self.invoke([])
        self.assertEqual(context.exception.code, 20)

    def test_current_platform_evidence(self):
        result = self.invoke([self.pr, self.run, self.jobs, self.pr])
        self.assertEqual(result["state"], "READY_TO_MERGE")
        self.assertFalse(result["authorizes_merge"])

    def test_wrong_head_rejected(self):
        self.pr["headRefOid"] = "c" * 40
        with self.assertRaises(GateError) as context:
            self.invoke([self.pr])
        self.assertEqual(context.exception.code, 11)

    def test_same_name_other_workflow_not_accepted(self):
        self.run["workflow_runs"][0]["path"] = ".github/workflows/fake.yml"
        with self.assertRaises(GateError) as context:
            self.invoke([self.pr, self.run])
        self.assertEqual(context.exception.code, 11)

    def test_skipped_job_is_rejected(self):
        self.jobs["jobs"][0]["conclusion"] = "skipped"
        with self.assertRaises(GateError) as context:
            self.invoke([self.pr, self.run, self.jobs])
        self.assertEqual(context.exception.code, 12)

    def test_new_push_during_query_rejected(self):
        fresh = dict(self.pr, headRefOid="d" * 40)
        with self.assertRaises(GateError) as context:
            self.invoke([self.pr, self.run, self.jobs, fresh])
        self.assertEqual(context.exception.code, 11)

    def test_missing_approval_rejected(self):
        self.pr["reviewDecision"] = "REVIEW_REQUIRED"
        with self.assertRaises(GateError) as context:
            self.invoke([self.pr])
        self.assertEqual(context.exception.code, 13)
