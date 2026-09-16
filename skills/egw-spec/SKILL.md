---
name: egw-spec
description: 为 Codex 任务建立并校验 task-contract.json、规格和待批准材料；适用于新任务或需求不明确时，不开始业务实现。
---

# EGW Spec：建立任务合同

本 Skill 负责把用户请求变成可验证、可审批的任务合同。它只准备规格阶段的材料，不代表用户批准了任务，也不开始业务代码实现。

## 路径与调用约定

本文件位于 `<插件根>/skills/egw-spec/SKILL.md`。相对本文件自身的 CLI 候选路径是 `../../scripts/egw.py`；执行前必须从本文件自身的绝对路径解析插件根目录并规范化为绝对路径。业务项目是 `--root` 的另一个目录，不能假设业务项目存在 `scripts/egw.py`。

```bash
# SKILL_FILE 必须替换为本 SKILL.md 的实际绝对路径。
SKILL_FILE="/absolute/path/to/evidence-gated/skills/egw-spec/SKILL.md"
PLUGIN_ROOT="$(cd "$(dirname "$SKILL_FILE")/../../" && pwd)"
PROJECT="/absolute/path/to/the-business-project"
python3 "$PLUGIN_ROOT/scripts/egw.py" status --root "$PROJECT" --json
```

实际执行时，命令必须等价于：

```text
python3 "<已解析的绝对插件根>/scripts/egw.py" ...
```

不要使用相对的业务项目脚本路径，不要引入其他宿主的变量、Hook 或命令格式。

## 适用条件

- 用户要开始一个新功能、修复或可单独验收的工程任务。
- 需求、范围、风险或验收条件还需要明确。
- 当前任务使用 MVP 固定的 `software-python-retry` profile。

MVP 只接受低风险、纯函数边界示例。遇到医疗、科研、高风险、外部系统、凭据、部署或不受支持的语言时，停止并报告需要另行设计；不要通过修改风险字段把任务伪装成低风险任务。

## 规格阶段流程

1. 确认业务项目的绝对路径、任务 ID 和用户目标。任务 ID 应稳定地用于 `tasks/<ID>/`；缺少关键信息时只询问必要问题，不猜测验收标准。
2. 运行：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" status --root "$PROJECT" --json
   ```

   读取现有合同、任务材料和状态。不要直接编辑 `.egw/state.json` 或事件日志。

3. 如果项目还没有合同，运行：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" init \
     --root "$PROJECT" \
     --task TASK-001 \
     --objective "用户确认的目标"
   ```

   `profile` 使用 CLI 默认的 `software-python-retry`；不要在 MVP 中另造 profile。`init` 只创建草稿合同和任务材料，不批准、不签名、不改业务代码。
4. 只读取足以判断范围的项目入口、测试布局和相关模块。可以参考 [上游规格驱动方法](../../upstream/agent-skills/skills/spec-driven-development/SKILL.md)，但上游关于 Git、提交、多 Agent 或宿主适配的建议必须服从本项目合同与用户授权。
5. 在 `task-contract.json` 和 `tasks/TASK-001/spec.md` 中明确：目标、非目标、允许路径、禁止路径、风险、数据分类、操作边界、验收条件、必需证据和审批要求。每个验收条件必须引用已注册的验证器，例如 `retry-boundaries-v1`；禁止在合同中提供任意 Shell 命令。
6. 运行：

   ```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" spec --root "$PROJECT"
   ```

   让 CLI 校验合同并生成或刷新待批准材料。校验失败就修正规格内容或报告阻塞，不能删减项目最低策略来获得通过。
7. 检查 `tasks/<ID>/` 中的 `spec.md`、`plan.md`、`baseline.json` 和 `approval-request.json` 是否属于当前任务。它们是待批准输入；外部人工环境产生的 `approval-request.json.sig` 不由本 Skill 创建。

## 合同边界

规格必须保持以下关系：

| 项目 | 规则 |
|---|---|
| 合同文件 | 固定为业务项目根目录的 `task-contract.json` |
| 任务文件 | 固定为 `tasks/<ID>/spec.md`、`plan.md`、`baseline.json`、`approval-request.json` 及外部提供的 `.sig` |
| 允许路径 | 只覆盖当前功能源文件、测试和任务材料 |
| 受保护路径 | `workflow/`、`verifiers/`、`scripts/`、`skills/`、插件元数据、上游快照、CI 和规则文件不能由任务扩大或修改 |
| 验收条件 | 每条都要能映射到注册验证器或明确标记为人工判断 |
| 审批 | 规格或计划变化会使已有审批请求失效；不能由 Agent 自行批准 |

不要把 Markdown 中写下的“已批准”当成审批事实。有效执行门禁由外部人工 SSH 签名和受信任策略共同确认。

## 必须停止的情况

- 合同 JSON 无效、重复字段、路径逃逸或存在未知字段。
- 任务要求超出 `software-python-retry` profile，或要求修改治理文件。
- 需要读取私钥、凭据、患者资料或向外部服务上传内容。
- 用户目标无法形成明确验收条件。
- CLI、策略或必要材料缺失。

停止时说明失败代码、具体文件或字段、解除条件；不要自行降级风险、跳过审批、生成签名或改动状态。

## 输出模板

```text
规格阶段：SPECIFIED / BLOCKED
合同：task-contract.json
任务材料：tasks/<ID>/spec.md、plan.md、baseline.json、approval-request.json
范围：<允许修改的路径>
验收：<AC ID -> verifier>
校验：<egw spec 的结果和退出码>
待批准事项：<需要人工确认的内容>
下一步：通过外部审批后运行 egw-plan；当前不执行实现。
```

本 Skill 不提交、推送、创建或合并 PR，不部署，不安装依赖，不调用子代理，也不自动执行 Git 操作。
