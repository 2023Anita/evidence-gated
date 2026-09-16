# 兼容性说明

本文描述 Evidence-Gated Workflow 当前 MVP 的实际支持边界。当前版本只建设 Codex 应用适配，不提供新的 Claude Code 或其他宿主适配层。

## 支持矩阵

| 组件 | 支持范围 | 说明 |
|---|---|---|
| 宿主 | Codex 应用／Codex CLI 的插件与 Skill 入口 | 通过 `.codex-plugin/plugin.json` 和根目录 `skills/` 发现；宿主是否实际加载仍需运行时验收 |
| Python | `>=3.12` | CLI 与治理模块按 Python 3.12 语法和标准库设计 |
| 操作系统 | macOS、Linux | `fcntl`、`resource`、`ssh-keygen -Y verify` 和 Docker 路径是默认验证流程的一部分 |
| Windows | 未验证 | 不把 Windows 可运行或可隔离作为当前承诺；需要单独验证锁、资源限制、SSH 和 Docker 行为 |
| 验证模式 | 默认 Docker；`--local` 为显式允许的本地预检查 | Docker 模式无网络、只读候选挂载、固定镜像摘要；`--local` 非隔离且不能冒充 CI |
| 任务 profile | `software-python-retry` | MVP 固定低风险纯函数示例；其他语言、医疗／科研和高风险任务需另行设计 |
| 合同 | 业务项目根目录 `task-contract.json` | 任务材料位于 `tasks/<ID>/`，审批签名由外部人工环境提供 |

## CLI 路径

CLI 属于插件根目录，业务项目只是 `--root` 目标。所有调用应使用解析后的绝对插件路径：

```bash
python3 "/absolute/path/to/evidence-gated/scripts/egw.py" status \
  --root "/absolute/path/to/business-project" \
  --json
```

五个 Codex Skill 从自身文件位置解析插件根：`<插件根>/skills/<skill-name>/SKILL.md` 的 `../../` 是插件根，再调用 `<插件根>/scripts/egw.py`。因此业务项目不需要、也不应复制 `scripts/egw.py`。当前包不使用其他宿主的环境变量或 Hook 约定。

## 运行时依赖与限制

- `jsonschema` 等 Python 依赖必须在受信任环境中预先提供；CLI 不自动执行 `pip install`，不做全局安装，也不从网络下载依赖。
- 默认 `verify` 要求 Docker 可用，且策略指定的固定镜像摘要已经由维护者在可信环境准备好。Docker 不可用时报告基础设施失败，不回退为主机执行。
- `verify --local` 只适用于用户明确允许的可信候选代码预检查。它在当前主机进程中运行，结果必须标记为本地预检查，不能成为 CI Required Check、人工审批或合并依据。
- 执行门禁依赖受信任策略中的 `workflow/policies/allowed_signers` 和外部人工生成的 `approval-request.json.sig`。插件不提供签名命令，不读取私钥。
- 当前 MVP 不执行自动提交、推送、创建或合并 PR、部署、发布、上传或生产系统调用。

## 元数据与运行时加载

`.codex-plugin/plugin.json` 的 JSON 语法、字段和路径可以由静态检查验证；静态元数据校验通过，只说明文件格式和声明满足检查条件，不等于目标 Codex 运行时已经发现、加载或执行该插件。运行时兼容性必须单独验证：

1. 在目标 Codex 应用／CLI 中安装或启用本插件。
2. 确认 `egw-*` Skill 能被发现并读取其 `SKILL.md`。
3. 用真实业务项目执行 `status --root ... --json`，确认 CLI 使用的是插件绝对路径。
4. 在不修改业务代码的试验任务上验证 `init`、`spec`、`gate`、`verify` 和 `status` 的退出码与阻断行为。

本仓库的静态校验、Python 单元测试或文件存在性检查不能单独证明以上运行时加载结果。

## 上游快照边界

`upstream/agent-skills/` 是固定提交的来源快照，当前仅包含 `skills/`、`references/`、`LICENSE` 和 `README.md`；文件摘要见 `upstream/manifest.json`。快照不会由 CLI 自动全量加载，也不会自动替换本项目的 Codex Skill。各 Skill 只在需要时显式引用对应的上游工作方法。

快照清单用于来源追溯和完整性复核，不是任务验证器，不是 CI Required Check，也不是合并硬门禁。更新快照时必须先固定新的上游 commit，逐文件复核路径、数量、大小和 SHA256，再重新审查本项目的策略与 Codex 入口。

## 宿主适配范围

当前版本只维护 Codex 适配：

- Codex 元数据：`.codex-plugin/plugin.json`。
- Codex Skill：`skills/egw-spec`、`egw-plan`、`egw-build`、`egw-verify`、`egw-ship`。
- 共享执行入口：插件根目录 `scripts/egw.py`。

当前版本没有新增 Claude Code 命令、Hooks、插件元数据或适配层；不存在“两个宿主行为一致”的兼容承诺。若未来增加宿主，必须单独记录入口、路径解析、权限边界和实测版本，不能把 Codex 的静态检查结果当作新宿主的运行时证明。
