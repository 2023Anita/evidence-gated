# 上游来源与快照说明

本项目以 [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) 为衍生基础，复用其中面向 AI 编程 Agent 的工程 Skills 与参考材料，并在此之上增加 Evidence-Gated Workflow 的任务合同、状态、策略、验证和证据记录能力。上游内容是工作流提示词与参考资料；本项目的治理 CLI、策略与验证器属于新增实现。

## 固定来源

- 仓库：`https://github.com/addyosmani/agent-skills`
- 固定提交：`be4e44a9fbc5e8df0beaefadbb28bd22ee61cc39`
- 对应版本：上游插件元数据版本 `0.6.9`
- 快照位置：`upstream/agent-skills/`
- 完整清单：`upstream/manifest.json`
- 快照文件数：39

快照只包含固定提交中的 `skills/`、`references/`、`LICENSE` 和 `README.md`。本版本没有复制上游的 Claude Code 适配层，也不包含 `.claude/`、`.claude-plugin/`、Hooks 或其他宿主专属目录；本版本只建设 Codex 应用适配。根目录的治理代码和 `skills/` 扩展由本项目独立维护。

`upstream/manifest.json` 记录每个快照文件的来源路径、上游 Git blob SHA、文件大小和 SHA256。清单用于来源追溯和完整性复核，不能替代任务验证，也没有被定义为 CI Required Check 或合并硬门禁。快照中的 Markdown 规则和 Agent 自评同样不构成硬约束；硬门禁由受信任的验证器、CI 和仓库保护规则共同提供。

## 许可证与署名

快照保留上游的 [MIT License](upstream/agent-skills/LICENSE)。上游文件及其衍生部分继续保留 `Copyright (c) 2025 Addy Osmani` 和 MIT 许可声明；分发本项目或包含上游实质内容的副本时，必须同时保留该版权与许可文本。本项目新增代码和文档按本项目根目录的许可证安排，并在发生实质改写时保持上游来源可追溯。

## 更新流程

更新上游时，不直接跟随浮动分支复制内容，按以下步骤生成新的候选快照：

1. 先选定并记录一个完整的上游 commit SHA，读取该提交的 Git tree API。
2. 只选择 `skills/`、`references/`、`LICENSE` 和 `README.md` 下的文件；发现空列表、越界路径、下载失败、数量不一致或大小不一致时，更新失败。
3. 通过该 commit 的 raw 文件地址下载到临时位置，逐个以来源 tree 的 blob SHA 和本地 SHA256 复核后，再替换 `upstream/agent-skills/`。
4. 重新生成 `upstream/manifest.json`，检查清单数量、文件路径、文件大小和 SHA256 可复算。
5. 对上游变更做人工差异审查，并重新运行本项目的合同、状态、验证器和 Codex 适配检查；上游更新不能自动改变项目策略或任务合同。
6. 在 `UPSTREAM.md` 中同步新的 commit、版本、文件数和更新说明，保留旧版本的来源记录以便回溯。

快照更新是依赖维护动作，应与普通任务实现分开审查。没有明确的上游 commit、完整的清单和通过的完整性复核时，不把候选内容作为项目来源使用。
