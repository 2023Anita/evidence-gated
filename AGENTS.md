# Evidence-Gated Codex 开发约定

本目录是 Codex 专用工程治理插件，不新增 Claude 适配、Hooks 或其他宿主包装。

- 首先阅读 README.md、docs/threat-model.md 和当前变更相关模块。
- 保留固定上游核心快照及版权；更新快照必须重新验证 upstream/manifest.json。
- 不把本地报告、本地状态、mock 测试或 --ci 标志当作平台可信证据。
- 不接触正式批准者私钥；只在测试临时目录创建明确的测试身份。
- 合同不能降低项目最低策略，不添加跳过失败或强制批准开关。
- 候选代码不能带着 Token 在宿主运行。默认 Docker 不可用时必须失败。
- 未经用户明确要求，不进行 Git 初始化、分支、提交、推送、发布或全局配置修改。
- 修改后运行相关 unittest；结构变化运行 scripts/validate_bundle.py。

主目录的 graphify 重建要求仍适用；环境缺少 graphify 时报告缺失，不擅自全局安装。
