---
name: egw-build
description: 在已签署任务合同和批准范围内实施低风险代码变更，并把结果交给独立验证；不适用于未审批或超出固定 profile 的任务。
---

# EGW Build：实施批准的变更

本 Skill 只在执行门禁通过后修改业务项目。它负责按已批准计划实施最小变更，不负责批准合同、修改治理层或执行交付动作。

## 路径与调用约定

本文件位于 `<插件根>/skills/egw-build/SKILL.md`。相对本文件自身的 CLI 候选路径是 `../../scripts/egw.py`；从本文件自身的绝对路径解析插件根目录后，所有 CLI 调用都必须使用解析后的绝对路径。`PROJECT` 是业务项目根目录，不能假设业务项目存在 `scripts/egw.py`。

```bash
# SKILL_FILE 必须替换为本 SKILL.md 的实际绝对路径。
SKILL_FILE="/absolute/path/to/evidence-gated/skills/egw-build/SKILL.md"
PLUGIN_ROOT="$(cd "$(dirname "$SKILL_FILE")/../../" && pwd)"
PROJECT="/absolute/path/to/the-business-project"
python3 "$PLUGIN_ROOT/scripts/egw.py" gate --root "$PROJECT" --checkpoint execute
```

实际命令必须等价于：

```text
python3 "<已解析的绝对插件根>/scripts/egw.py" ...
```

不要使用相对业务项目脚本路径，不要引入其他宿主的变量、Hook 或命令格式。

## 执行前门禁

开始任何业务代码写入前，运行：

```bash
   python3 "<已解析的绝对插件根>/scripts/egw.py" status --root "$PROJECT" --json
   python3 "<已解析的绝对插件根>/scripts/egw.py" gate --root "$PROJECT" --checkpoint execute
```

只有 `gate` 退出码为 `0` 才能执行。该门禁会重新验证当前合同、规格、计划、基线、允许签名者和外部 SSH 签名是否匹配；本地状态文件中写着 `APPROVED` 不足以放行。

默认策略是低风险固定 `software-python-retry` profile。执行门禁拒绝、外部签名缺失或无效、合同与审批内容不一致、策略文件不可用时，停止并报告具体原因。不要自行生成签名、读取私钥、修改 `allowed_signers`、降低风险、删除审批要求或手工推进状态。

## 实施规则

1. 读取当前 `task-contract.json`、`tasks/<ID>/spec.md`、`tasks/<ID>/plan.md`，只按计划中已列出的步骤工作。
2. 只修改合同 `scope.allowed_paths` 中的业务源文件、测试和任务材料。`workflow/`、`verifiers/`、`scripts/`、`skills/`、插件元数据、上游快照、CI、规则和依赖锁文件属于受保护范围。
3. 参考 [上游测试驱动方法](../../upstream/agent-skills/skills/test-driven-development/SKILL.md) 和 [增量实施方法](../../upstream/agent-skills/skills/incremental-implementation/SKILL.md)：先用小而明确的测试确认行为，再实现最小修复，并在每个逻辑切片后检查。上游要求提交的部分不适用于当前 Skill；本流程不自动执行 Git。
4. 不引入未批准依赖，不运行全局安装，不执行自动 `pip install`，不读取凭据，不联网下载代码或包。项目已有依赖只按批准环境使用。
5. 不把测试修改成只迎合预期结果。保留失败能区分边界的测试，尤其检查 Python `bool` 与整数边界的区别。
6. 如果实现需要修改合同范围、提高风险、改变验收条件、替换 verifier 或触及治理文件，立即停止，回到 egw-spec/egw-plan，不在实现阶段自我豁免。

## 验证方式

实现后优先运行默认隔离验证：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" verify \
  --root "$PROJECT" \
  --output ".egw/reports/local.json"
```

默认 `verify` 使用固定 Docker 镜像、无网络和只读候选挂载。Docker 不可用时应报告基础设施失败；不得自动回退为主机执行。

只有用户明确允许“可信代码预检查”时，才可以运行：

```bash
python3 "<已解析的绝对插件根>/scripts/egw.py" verify \
  --root "$PROJECT" \
  --local \
  --output ".egw/reports/local-advisory.json"
```

`--local` 在主机进程中执行，属于非隔离的本地预检查；报告必须保持 `local` 标记，永远不能写成 CI 通过、合并通过或已发布。无论本地结果如何，后续仍需默认 Docker 验证和平台门禁。

## 失败处理与输出

验证失败、超时、跳过、输出无效或证据绑定过期时，停止在当前步骤并报告 `FAIL` 或 `BLOCKED`。不要手工修改 `.egw` 报告，不要复用另一提交的通过报告。修复后重新运行 `verify`；若合同或计划变化，重新走规格和外部审批。

```text
实施阶段：EXECUTING / BLOCKED / FAILED
变更：<实际修改的允许路径>
验收：<AC ID -> 结果>
验证：<默认 Docker 或明确授权的 local，退出码和报告路径>
剩余阻塞：<签名、Docker、失败检查或范围问题>
下一步：验证通过后运行 egw-verify/egw-ship；不自动提交或推送。
```

本 Skill 不提交、推送、创建或合并 PR，不部署，不签署审批，不安装依赖，不调用子代理，也不自动执行 Git 操作。
