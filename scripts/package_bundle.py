#!/usr/bin/env python3
"""填充已通过插件 scaffold 创建的本地分发目录，不写全局配置。"""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "distribution"
PLUGIN = DIST / "plugins/evidence-gated"
DIRECTORIES = (".codex-plugin", ".agents", "skills", "workflow", "verifiers", "scripts", "examples",
               "upstream", "docs", "tests", "templates", ".github", "assets")
FILES = ("README.md", "LICENSE", "UPSTREAM.md", "AGENTS.md", "CONTRIBUTING.md", "SECURITY.md",
         "CHANGELOG.md", "pyproject.toml",
         "requirements-governance.lock", ".gitignore")


def main():
    marketplace = DIST / ".agents/plugins/marketplace.json"
    if not marketplace.is_file() or not (PLUGIN / ".codex-plugin/plugin.json").is_file():
        raise SystemExit("请先使用 plugin-creator scaffold 在 distribution 创建本地 marketplace 和插件目录。")
    for name in DIRECTORIES:
        shutil.copytree(ROOT / name, PLUGIN / name, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"))
    for name in FILES:
        shutil.copy2(ROOT / name, PLUGIN / name)
    source_paths = set()
    for name in DIRECTORIES:
        source_paths.update(p.relative_to(ROOT).as_posix() for p in (ROOT / name).rglob("*")
                            if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and p.name != ".DS_Store")
    source_paths.update(FILES)
    actual = {p.relative_to(PLUGIN).as_posix() for p in PLUGIN.rglob("*") if p.is_file()}
    if actual != source_paths:
        raise SystemExit("分发目录含过期或意外文件；请使用新输出目录重新 scaffold，不自动删除。")
    checksums = {}
    for name in sorted(source_paths):
        data = (PLUGIN / name).read_bytes()
        if data != (ROOT / name).read_bytes():
            raise SystemExit("分发内容与源码不一致：" + name)
        checksums[name] = hashlib.sha256(data).hexdigest()
    archive = DIST / "evidence-gated-codex-0.1.0.zip"
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.write(marketplace, ".agents/plugins/marketplace.json")
        for name in sorted(source_paths):
            bundle.write(PLUGIN / name, "plugins/evidence-gated/" + name)
    manifest = {"version": "0.1.0", "file_count": len(checksums), "files": checksums,
                "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}
    (DIST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"package": str(archive), "files": len(checksums), "sha256": manifest["archive_sha256"]}))


if __name__ == "__main__":
    main()
