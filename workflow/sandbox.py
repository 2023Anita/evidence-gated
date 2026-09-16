"""固定验证器进程；本地执行明确不冒充安全沙箱。"""

from __future__ import annotations

import json
import os
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from .common import GateError, read_bytes, safe_path


def limits():
    resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


def run_check(root: Path, trusted: Path, policy: dict, mode: str, local: bool):
    # 只复制此 profile 必需文件，绝不挂载整个仓库、.git 或潜在的现存凭据。
    with tempfile.TemporaryDirectory(prefix="egw-subject-") as directory:
        staging = Path(directory)
        subject = staging / "candidate"
        for name in policy["required_files"]:
            target = subject / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_bytes(safe_path(root, name)))
        driver = staging / "trusted/verifiers/software/runner.py"
        driver.parent.mkdir(parents=True)
        driver.write_bytes(read_bytes(trusted / "verifiers/software/runner.py"))
        return _run_check(subject, staging / "trusted", policy, mode, local)


def _run_check(root: Path, trusted: Path, policy: dict, mode: str, local: bool):
    driver = trusted / "verifiers/software/runner.py"
    container_name = "egw-" + uuid.uuid4().hex
    if local:
        command = [sys.executable, "-I", "-B", str(driver), mode, str(root)]
    else:
        image = policy["container_image"]
        if not re.fullmatch(r"python@sha256:[0-9a-f]{64}", image):
            raise GateError(20, "INFRA_ERROR：可信策略必须固定容器镜像摘要")
        if not shutil.which("docker"):
            raise GateError(20, "INFRA_ERROR：Docker 不可用；CI 不允许回退为主机执行")
        try:
            inspect = subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=20)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GateError(20, "INFRA_ERROR：Docker daemon 无法响应") from error
        if inspect.returncode:
            raise GateError(20, "INFRA_ERROR：固定镜像未就绪；请在可信环境预拉取策略中的镜像")
        command = [
            "docker", "run", "--rm", "--name", container_name,
            "--network", "none", "--read-only", "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges", "--pids-limit", "64",
            "--memory", "256m", "--cpus", "1", "--user", "65534:65534",
            "--tmpfs", "/tmp:rw,noexec,nosuid,nodev,size=16777216,mode=1777",
            "--mount", f"type=bind,src={root},dst=/candidate,readonly",
            "--mount", f"type=bind,src={driver.parent},dst=/verifier,readonly",
            "--workdir", "/tmp", image,
            "python", "-I", "-B", "/verifier/runner.py", mode, "/candidate",
        ]
    # 绝不把 Agent / GitHub 环境、密钥、Python 路径注入待测进程。
    environment = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if not local:
        # Docker CLI 需找到默认 socket；不传递其他调用者环境。
        environment["PATH"] = str(Path(shutil.which("docker")).parent) + os.pathsep + os.defpath
    with tempfile.TemporaryDirectory(prefix="egw-run-") as working, tempfile.TemporaryFile() as output:
        process = None
        try:
            process = subprocess.Popen(command, cwd=working, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                                       start_new_session=True, preexec_fn=limits)
            process.wait(timeout=policy["timeout_seconds"])
        except subprocess.TimeoutExpired as error:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise GateError(12, f"CHECK_FAILED：{mode} 超时") from error
        except OSError as error:
            raise GateError(20, f"INFRA_ERROR：无法启动 {mode}") from error
        finally:
            if not local:
                try:
                    subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=20)
                except (OSError, subprocess.TimeoutExpired) as error:
                    raise GateError(20, "INFRA_ERROR：无法确认测试容器已停止，请人工检查 Docker") from error
        output.seek(0)
        raw = output.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise GateError(12, f"CHECK_FAILED：{mode} 输出超过限制")
    try:
        result = json.loads(raw.decode().strip().splitlines()[-1])
        valid = (isinstance(result, dict) and result.get("mode") == mode
                 and type(result.get("tests_run")) is int and result["tests_run"] > 0
                 and result.get("skipped") == 0 and result.get("success") is True)
    except (ValueError, IndexError, UnicodeError):
        valid, result = False, {}
    if process.returncode != 0 or not valid:
        raise GateError(12, f"CHECK_FAILED：{mode} 失败、跳过或未产生有效报告（退出码 {process.returncode}）")
    return {"id": mode, "result": "PASS", "tests_run": result["tests_run"], "skipped": 0,
            "isolation": "local-process-not-sandboxed" if local else "docker-no-network"}
