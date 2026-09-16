#!/usr/bin/env python3
"""验证分发结构、Skill 元数据、Schema 和固定上游来源。"""

import hashlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]


def main():
    plugin = json.loads((ROOT / ".codex-plugin/plugin.json").read_text())
    assert plugin["name"] == "evidence-gated"
    assert plugin["skills"] == "./skills/"
    expected = {"egw-spec", "egw-plan", "egw-build", "egw-verify", "egw-ship"}
    assert {p.name for p in (ROOT / "skills").iterdir() if p.is_dir()} == expected
    for name in expected:
        text = (ROOT / "skills" / name / "SKILL.md").read_text()
        assert text.startswith("---\n") and f"name: {name}\n" in text and "description: " in text
        assert "CLAUDE_PLUGIN_ROOT" not in text and "CLAUDE_PROJECT_DIR" not in text
    for name in ("task-contract", "evidence", "approval"):
        schema = json.loads((ROOT / f"workflow/schemas/{name}.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
    manifest = json.loads((ROOT / "upstream/manifest.json").read_text())
    assert manifest["source"]["commit"] == "be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39"
    assert manifest["file_count"] == len(manifest["files"])
    paths = set()
    for item in manifest["files"]:
        path = ROOT / "upstream" / item["path"]
        data = path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == item["sha256"], item["path"]
        assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == item["source_blob_sha"]
        assert len(data) == item["size"]
        paths.add(path.relative_to(ROOT / "upstream/agent-skills").as_posix())
    actual = {p.relative_to(ROOT / "upstream/agent-skills").as_posix()
              for p in (ROOT / "upstream/agent-skills").rglob("*") if p.is_file()}
    assert actual == paths
    assert not (ROOT / ".claude").exists()
    assert not (ROOT / ".claude-plugin").exists()
    print(json.dumps({"bundle": "PASS", "codex_skills": 5, "upstream_files": len(paths),
                      "claude_adapter": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
