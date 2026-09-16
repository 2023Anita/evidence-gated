---
name: egw-plan
description: 根据有效任务合同生成可审批的 plan.md 和验证步骤；适用于已经明确目标、需要拆分实施工作的 Codex 任务。
---

# EGW Plan：生成实施计划

本 Skill 把已经形成的任务规格拆成小而可核验的实施步骤。计划是审批输入，不是执行授权；它不能扩大合同范围，也不能替用户签署批准。

## 路径与调用约定

本文件位于 `<插件根>/skills/egw-plan/SKILL.md`。相对本文件自身的 CLI 候选路径是 `../../scripts/egw.py`；从本文件自身的绝对路径解析插件根目录后，再使用绝对的 CLI 路径。`PROJECT` 指业务项目根目录，不能假设业务项目内有 `scripts/egw.py`。

```bash
# SKILL_FILE 必须替换为本 SKILL.md 的实际绝对路径。
SKILL_FILE="/absolute/path/to/evidence-gated/skills/egw-plan/SKILL.md"
PLUGIN_ROOT="$(cd "$(dirname "$SKILL_FILE")/../../" && pwd)"
PROJECT="/absolute/path/to/the-business-project"
python3 "$PLUGIN_ROOT/scripts/egw.py" status --root "$PROJECT" --json
```

命令必须使用解析后的绝对插件路径：

```text
python3 "<已解析的绝对插件根>/scripts/egw.py" ...
```

不要调用业务项目的相对脚本，不要使用其他宿主的变量、命令或适配层。

## 前置条件

1. 运行：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" status --root "$PROJECT" --json
   ```

2. 确认 `task-contract.json`、`tasks/<ID>/spec.md` 存在且对应同一个任务。
3. 运行 `spec` 重新校验当前材料：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" spec --root "$PROJECT"
   ```

规格校验失败、任务 ID 不一致或 profile 不受支持时，回到 egw-spec 并报告原因。不要开始业务实现。

## 计划内容

参考 [上游任务拆分方法](../../upstream/agent-skills/skills/planning-and-task-breakdown/SKILL.md) 和 [增量实施方法](../../upstream/agent-skills/skills/incremental-implementation/SKILL.md)，只提取适合本任务的做法。上游关于提交、发布、多 Agent 或自动协调的建议不在本 Skill 的授权范围内。

在 `tasks/<ID>/plan.md` 写出以下内容：

```markdown
# Implementation Plan: <任务名称>

## 目标与边界
- 目标：<合同 objective>
- 非目标：<明确排除项>
- 允许修改：<合同中的允许路径>

## 实施步骤
1. <最小变更>：文件 <path>；对应 AC-001；检查 <可复现的检查>
2. <下一个变更>：文件 <path>；对应 AC-002；检查 <可复现的检查>

## 验证映射
| AC ID | 注册 verifier | 预期证据 |
|---|---|---|
| AC-001 | retry-boundaries-v1 | trusted-acceptance-tests |

## 失败与回退
- 失败时停止在哪个步骤：<条件>
- 回退方式：<可逆的文件变更或重新回到规格阶段>

## 未决问题
- <需要人工决定的问题；没有则写“无”>
```

每个步骤只能修改合同允许的路径；步骤必须能独立说明目标、验收条件和检查方式。禁止把“运行全部测试”“看起来正常”作为唯一证据。项目测试命令可以记录在计划中，但不能代替受信任 verifier。

## 生成与审批

完成 `plan.md` 后运行：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" spec --root "$PROJECT"
```

CLI 会重新校验合同并刷新与当前合同、规格、计划和基线相关的待批准材料。确认 `tasks/<ID>/approval-request.json` 绑定当前内容后，向用户展示计划并等待人工在独立环境签署 `approval-request.json.sig`。

本 Skill 不提供签名命令、不读取私钥、不写入签名文件、不把聊天中的“同意”伪造成签名，也不直接把状态推进到 `APPROVED` 或 `EXECUTING`。只有外部人工 SSH 签名能满足执行门禁要求。

## 计划变更规则

- 改变目标、风险、允许路径、必需证据、验收条件或验证器映射时，必须回到规格阶段。
- 计划触及 `workflow/`、`verifiers/`、`scripts/`、`skills/`、插件元数据、CI 或上游快照时，停止并报告策略拒绝。
- 计划新增外部网络、凭据、上传、部署或高风险操作时，停止并请求重新设计；不要修改合同降低风险。
- 已签署审批请求与计划摘要不一致时，审批失效，必须生成新的待批准材料。

## 输出模板

```text
计划阶段：SPECIFIED / BLOCKED
合同：task-contract.json（校验结果）
计划：tasks/<ID>/plan.md
步骤：<数量及对应 AC ID>
验证：<verifier 映射和项目检查>
审批：approval-request.json 已生成；外部签名 <存在/缺失/不匹配>
下一步：签名通过后运行 egw-build；当前不修改业务代码。
```

本 Skill 不提交、推送、创建或合并 PR，不部署，不安装依赖，不调用子代理，也不自动执行 Git 操作。
