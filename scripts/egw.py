#!/usr/bin/env python3
"""从插件自身路径加载核心，不依赖业务仓库工作目录。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    from workflow.cli import main
except ModuleNotFoundError as error:
    import json
    print(json.dumps({"ok": False, "exit_code": 20,
                      "message": f"INFRA_ERROR：插件文件不完整，缺少模块 {error.name}。"}, ensure_ascii=False), file=sys.stderr)
    raise SystemExit(20)

if __name__ == "__main__":
    raise SystemExit(main())
