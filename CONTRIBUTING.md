# 参与贡献

感谢你帮助 Evidence-Gated 变得更可靠。这个项目更看重“小、硬、可验证”的改动。

## 适合的贡献

- 一个有明确输入输出和失败案例的低风险 profile。
- 一个能复现真实绕过方式的测试。
- 更清楚的安装、错误提示和中文文档。
- macOS、Linux、Python 3.12+ 或 Docker 的兼容性修复。

请把医学、财务、生产凭据、自动部署和广泛权限模型作为独立设计提案，不要混入普通修复。

## 本地检查

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --require-hashes -r requirements-governance.lock
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/validate_bundle.py
.venv/bin/python scripts/demo.py
```

运行时核心只依赖 Python 标准库；锁定依赖用于开发测试和 Schema 交叉验证。

## 提交要求

一个变更解决一个问题。PR 请说明 Motivation、Behavior、Verification 和 Risk。

不要提交真实密钥、Token、Cookie、患者数据、业务私有材料、`.venv/`、`.egw/` 或 `graphify-out/`。

新增 profile 时必须同时提供：合同限制、固定验证器、成功案例、真实失败案例、超时/跳过处理以及边界文档。
