"""五个命令，无提交、签署、推送或部署能力。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import GateError
from .engine import Engine
from .state import locked

TRUSTED_ROOT = Path(__file__).resolve().parents[1]


def parser():
    top = argparse.ArgumentParser(prog="egw", description="Codex 专用证据治理 MVP")
    subs = top.add_subparsers(dest="command", required=True)
    for name in ("init", "spec", "gate", "verify", "status"):
        sub = subs.add_parser(name)
        sub.add_argument("--root", type=Path, default=Path.cwd(), help="待治理项目根目录")
        if name == "init":
            sub.add_argument("--task", required=True)
            sub.add_argument("--objective", required=True)
        elif name == "gate":
            sub.add_argument("--checkpoint", choices=("execute", "review", "merge"), required=True)
            sub.add_argument("--pr", type=int)
        elif name == "verify":
            sub.add_argument("--local", action="store_true", help="明确允许本地非沙箱测试，只用于可信代码")
            sub.add_argument("--ci", action="store_true", help="在 CI 中绑定 Git 上下文，禁止本地后端")
            sub.add_argument("--output", type=Path)
            sub.add_argument("--base-sha")
            sub.add_argument("--head-sha")
            sub.add_argument("--candidate-sha")
        elif name == "status":
            sub.add_argument("--json", action="store_true", help="输出结构化状态（默认也是 JSON）")
    return top


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if not args.root.is_dir() or args.root.is_symlink():
            raise GateError(2, "INVALID_INPUT：项目根目录须存在且不能是符号链接")
        engine = Engine(args.root, TRUSTED_ROOT)
        if args.command == "status":
            result = engine.status()
        else:
            with locked(engine.root):
                if args.command == "init":
                    result = engine.init(args.task, args.objective)
                elif args.command == "spec":
                    result = engine.spec()
                elif args.command == "verify":
                    result = engine.verify(local=args.local, ci=args.ci, output=args.output,
                                           base=args.base_sha, head=args.head_sha, candidate=args.candidate_sha)
                elif args.checkpoint == "execute":
                    result = engine.execute()
                elif args.checkpoint == "review":
                    result = engine.review()
                else:
                    from .github import merge_gate
                    result = merge_gate(engine, args.pr)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except GateError as error:
        print(json.dumps({"ok": False, "exit_code": error.code, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
        return error.code
    except (OSError, ValueError) as error:
        print(json.dumps({"ok": False, "exit_code": 20, "message": f"INFRA_ERROR：{type(error).__name__}"}, ensure_ascii=False), file=sys.stderr)
        return 20
