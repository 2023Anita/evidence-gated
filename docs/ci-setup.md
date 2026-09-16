# CI 接入与平台验收

当前只交付模板，没有创建 GitHub 仓库、推送代码或更改规则。

## 两种 CI 分开

- `.github/workflows/ci.yml`：检查插件自身源码、测试和上游快照。
- `templates/github/evidence-gate.yml`：安装到业务仓库 `.github/workflows/evidence-gate.yml`，验证实际任务。

## 引导顺序

1. 维护者先准备可信治理仓库，配置批准者公钥，固定完整提交。
2. 先在业务基线中落地证据工作流与 `.gitignore` 中的 `.egw/`、`__pycache__/` 等运行产物规则。
3. 配置仓库变量 `EGW_GOVERNANCE_REPOSITORY=owner/repo` 和 `EGW_GOVERNANCE_SHA=完整40位提交`。模板只读取该不可变治理版本，不执行 PR 里的验证器。
4. 保护工作流和仓库变量的修改权限，再将唯一 `evidence-gate` job 设置为 Required Check。
5. 主分支要求 PR、当前版本人工审批、最新基线，禁止 Agent bypass。不要开启 merge queue。
6. 从这个干净基线初始化任务，人工签署规格摘要，执行业务修改，再由获准身份提交/推送。
7. 在 PR 中重跑检查，确认基线与合并候选双亲一致，人工完成代码审查。

如果治理仓库私有，默认 GITHUB_TOKEN 可能不能跨仓库读取。需要另行设计最小只读权限；不能把管理员 PAT 放进模板，不能把令牌传给候选容器。本版模板按可读取治理仓库设计，未配置就拒绝。

## 必须保护真实来源

个人仓库普通同名 Required Check 不能排除所有工作流替换。
根据实际套餐选择：组织 required workflow、受保护独立检查生产者，或支持路径限制的 Push Ruleset。CODEOWNERS 加强制审查可以增加人为防线，但不能直接宣称同等的防篡改隔离。

没有这些外部条件时，本系统只能标记为本地试点，不能声称“Agent 无法绕过”。

## `gate --checkpoint merge`

维护者完成上述部署后，在受保护治理版本的 `workflow/policies/github.json` 中设置：

```json
{
  "mode": "protected-workflow",
  "repository": "OWNER/REPOSITORY",
  "base_branch": "main",
  "required_check": "evidence-gate",
  "workflow_path": ".github/workflows/evidence-gate.yml"
}
```

`OWNER/REPOSITORY` 必须替换为真实业务仓库。该配置变化会改变治理摘要，任务须使用新治理版本重新批准。

CLI 用 GitHub CLI 进行只读查询，不自动登录，不输出令牌。检查当前 head、目标分支、人工批准、CLEAN 合并状态、指定工作流最新运行及 job。再次读取 PR 以排除普通新推送竞态。
这是当前条件快照，不是永久合并许可，也不自动执行合并。

## 平台验收表

| 情况 | 必须观察的结果 |
|---|---|
| bool 缺陷 | evidence-gate 失败且平台阻止合并 |
| 删除或跳过项目测试 | 失败 |
| 旧签名或改变计划 | 失败 |
| base 变化 | 要求新基线与审批 |
| 修改治理或工作流 | 平台阻止未经授权的治理变更 |
| 新提交复用旧运行 | 不满足当前提交门禁 |
| 没有人工审查 | 不可合并 |
| 完整通过且已审查 | 当前 PR 可以由授权人合并 |

本次未执行这些在线验收。GitHub mock 测试、YAML 解析和本地演示不能替代它们。

## 官方参考

- [GitHub Actions 安全](https://docs.github.com/en/actions/reference/security/secure-use)
- [分支保护](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)
- [Ruleset 与套餐边界](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/about-rulesets)
