---
name: egw-ship
description: 检查当前 Codex 任务是否满足审查和合并条件，并生成交付摘要；不自动提交、推送、合并、部署或发布。
---

# EGW Ship：评估交付条件

本 Skill 只负责交付前检查。它把当前合同、独立验证证据、人工审批和平台状态汇总为可审查结论；“ship”不代表获得了 Git 或部署权限。

## 路径与调用约定

本文件位于 `<插件根>/skills/egw-ship/SKILL.md`。相对本文件自身的 CLI 候选路径是 `../../scripts/egw.py`；从本文件自身的绝对路径解析插件根目录后，再调用绝对的 CLI 路径。`PROJECT` 是业务项目根目录，不能假设业务项目存在 `scripts/egw.py`。

```bash
# SKILL_FILE 必须替换为本 SKILL.md 的实际绝对路径。
SKILL_FILE="/absolute/path/to/evidence-gated/skills/egw-ship/SKILL.md"
PLUGIN_ROOT="$(cd "$(dirname "$SKILL_FILE")/../../" && pwd)"
PROJECT="/absolute/path/to/the-business-project"
python3 "$PLUGIN_ROOT/scripts/egw.py" status --root "$PROJECT" --json
```

所有命令都必须使用解析后的绝对插件路径：

```text
python3 "<已解析的绝对插件根>/scripts/egw.py" ...
```

不要使用相对业务项目脚本路径，不要引入其他宿主的变量、命令或适配层。

## 交付前顺序

1. 读取当前状态，不直接编辑 `.egw/state.json`：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" status --root "$PROJECT" --json
   ```

2. 确认本次候选代码已经用默认 Docker 模式验证。只有用户明确允许时，`--local` 结果才可以作为本地预检查参考；它永远不能替代 CI 或隔离验证。
3. 运行审查门禁：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" gate --root "$PROJECT" --checkpoint review
   ```

4. 如果需要平台合并条件，再运行：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" gate \
     --root "$PROJECT" \
     --checkpoint merge \
     --pr NUMBER
   ```

   `NUMBER` 必须是用户提供或现有材料明确关联的 PR 编号；未知时不要创建 PR 或猜测编号。没有 PR 时可以省略 `--pr` 以获得本地交付状态，但不能宣称满足平台合并门禁。

## 判定边界

交付结论必须区分：

| 结论 | 依据 |
|---|---|
| `REVIEWING` | 本地已生成当前版本证据，仍需审查或平台条件 |
| `READY_TO_MERGE` | 当前版本的可信验证、必需证据、合同签名、人工审查和平台 Required Check 均通过 |
| `BLOCKED` | Docker、策略、证据、审批或平台信息缺失／不可用 |
| `FAILED` | 至少一项必需检查失败或当前版本与证据不匹配 |
| `MERGED` | 只能依据平台实际显示的合并事实，不能由本地状态或 Agent 声称产生 |

旧版本报告、旧 PR 审批、聊天中的口头同意、手工改写的状态、`--local` 通过和 Agent 自评都不能单独产生 `READY_TO_MERGE`。合同、计划、验收、治理策略或代码发生变化时，相关证据和审批必须重新绑定当前版本。

可以参考 [上游发布检查表](../../upstream/agent-skills/skills/shipping-and-launch/SKILL.md) 组织审查问题，但不要自动执行其中的部署、发布、监控、提交或回滚动作；当前仓库只提供 Codex-only 的治理入口。

## 外部动作禁止自动触发

本 Skill 不执行以下动作：

- `git commit`、`git push`、创建或更新 PR。
- 合并 PR、修改分支保护、修改 Required Check 或仓库规则。
- 部署、发布、上传材料、发送消息或调用外部生产系统。
- 生成或读取 SSH 私钥、签署审批或替换受信任策略。

如用户另行明确授权某个外部动作，先报告已经完成的可审查结果和确切目标，再按该授权执行；`ship` 这个名称本身不构成授权。当前 Skill 内默认停在交付摘要和门禁结论。

## 输出模板

```text
交付阶段：REVIEWING / READY_TO_MERGE / BLOCKED / FAILED / MERGED
任务：<task ID>
验证：<Docker 报告路径、版本绑定和必需 evidence>
审批：<外部 SSH 签名和人工审查状态>
平台：<PR 编号、Required Check、分支规则状态；无 PR 则写“未检查”>
变更：<允许范围内的摘要>
限制：<没有证据支持的结论和仍需人工判断的事项>
下一步：<修复、补签、补证据或用户明确授权的外部动作>
```

本 Skill 不提交、推送、创建或合并 PR，不部署，不签署审批，不安装依赖，不调用子代理，也不自动执行 Git 操作。
