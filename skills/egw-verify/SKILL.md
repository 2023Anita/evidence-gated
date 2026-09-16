---
name: egw-verify
description: 对当前 Codex 任务运行独立验证并生成绑定版本的证据报告；默认使用 Docker，只有用户明确允许时才使用非隔离的本地预检查。
---

# EGW Verify：生成独立证据

本 Skill 负责重新计算当前任务是否满足合同的必需证据。它不能把 Agent 自评、旧报告或本地状态当成通过事实，也不负责自动修复业务代码。

## 路径与调用约定

本文件位于 `<插件根>/skills/egw-verify/SKILL.md`。相对本文件自身的 CLI 候选路径是 `../../scripts/egw.py`；从本文件自身的绝对路径解析插件根目录后，再调用绝对的 CLI 路径。`PROJECT` 指业务项目根目录，不能假设业务项目存在 CLI 脚本。

```bash
# SKILL_FILE 必须替换为本 SKILL.md 的实际绝对路径。
SKILL_FILE="/absolute/path/to/evidence-gated/skills/egw-verify/SKILL.md"
PLUGIN_ROOT="$(cd "$(dirname "$SKILL_FILE")/../../" && pwd)"
PROJECT="/absolute/path/to/the-business-project"
python3 "$PLUGIN_ROOT/scripts/egw.py" verify --root "$PROJECT"
```

实际执行命令必须使用解析后的绝对插件路径：

```text
python3 "<已解析的绝对插件根>/scripts/egw.py" ...
```

不要使用业务项目的 `scripts/egw.py`，不要引入其他宿主的变量、Hook 或命令格式。

## 验证前检查

先读取任务状态和合同，不修改状态文件：

```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" status --root "$PROJECT" --json
```

确认业务项目根、`task-contract.json`、任务 ID 和当前候选代码版本。合同、策略、验收映射或必要输入无效时，报告 `INVALID_CONTRACT` 或 `EVIDENCE_MISSING`，不要开始测试。

## 默认验证

默认命令使用受策略固定的 Docker 镜像运行可信 verifier：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" verify \
  --root "$PROJECT" \
  --output ".egw/reports/verify.json"
```

默认环境应是无网络、只读候选挂载、无 Agent 环境变量和无凭据的隔离进程。Docker 不可用、固定镜像未就绪、隔离运行器失败或输出无法解析时，报告 `INFRA_ERROR` 或 `CHECK_FAILED`；禁止自动回退为主机执行，也禁止把失败改写成通过。

验证器由受信任的插件代码和策略注册表选择。不要执行合同中提供的任意命令，不要加载业务项目自带的替代 verifier，不要让候选代码替换验证器或报告。

## `--local` 的严格边界

只有用户明确允许在当前主机对可信候选代码做预检查时，才运行：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" verify \
  --root "$PROJECT" \
  --local \
  --output ".egw/reports/verify-local-advisory.json"
```

`--local` 是非隔离的本地进程检查；它可能接触主机运行时能力，报告必须明确标记为本地预检查。`--local` 结果不能冒充 CI、Docker、平台 Required Check、人工审批或合并通过。即使本地通过，交付前仍需默认 Docker 验证。

## 证据报告规则

报告应逐项包含 `PASS`、`FAIL`、`BLOCKED` 或 `NEEDS_HUMAN`，并绑定：

- 当前 `task-contract.json` 的摘要。
- 当前受信任策略和 verifier 版本。
- 候选代码版本（base/head/candidate；按 CLI 能取得的版本记录）。
- 检查 ID、退出码、耗时、隔离方式和报告产物摘要。

下列情况都不算通过：缺失证据、跳过检查、超时、解析错误、旧合同、旧提交、手工修改报告、仅有 Agent 自评、项目测试与可信验收测试不一致。修复业务代码后重新运行完整验证，不只运行失败的一条并复用其他结果。

## 验证后动作

验证成功后，可检查审查门禁：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" gate --root "$PROJECT" --checkpoint review
```

此命令只读取当前证据和合同条件，不自动修改代码或状态。验证失败则转回 egw-build；合同、计划或验收条件变化则转回 egw-spec/egw-plan。不要直接写入 `READY_TO_MERGE`。

## 输出模板

```text
验证阶段：VERIFYING / REVIEWING / FAILED / BLOCKED
模式：Docker 隔离 / local 本地预检查（仅在用户明确允许时）
报告：<绝对或项目内报告路径>
结果：<每个 evidence ID、AC ID、verifier 和状态>
绑定：<合同、策略、verifier、候选版本摘要>
阻塞：<失败、超时、缺失、旧版本或人工签核>
下一步：<egw-build 修复、egw-ship 评估或人工处理>
```

本 Skill 不提交、推送、创建或合并 PR，不部署，不签署审批，不安装依赖，不调用子代理，也不自动执行 Git 操作。
