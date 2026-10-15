# Security policy · 安全政策

[English](#english) · [中文](#中文)

## English

### Scope

This repository contains a local-first desktop tool that reads local Codex authentication state to show quota and switch the active account.

Security-sensitive areas include token refresh and quota requests; account switching and replacement of the ambient session; Desktop restart helpers; Windows Desktop session backup and restore; and repository hygiene for screenshots, documentation, and sample data.

### Reporting a vulnerability

Do not include any of the following in a public issue:

- Access tokens, refresh tokens, or `auth.json` contents.
- Live quota/account snapshots or Desktop session snapshots.
- Private file paths or screenshots revealing real accounts.

Use GitHub private security reporting when it is available for this repository. If it is unavailable, open a minimal public issue without sensitive content and state that you can provide details privately. Do not post credentials while arranging a private report.

### Repository rules

- Never commit real `auth.json` files, live account snapshots, or live Desktop session backups.
- Never commit screenshots containing real account identities.
- Use synthetic examples for documentation and UI assets.
- Keep the full English and Chinese safety/privacy information consistent.
- Preserve required copyright attribution to the original [CodexControl by Adem Isler](https://github.com/ademisler/codexcontrol) and third-party authors. This project improves upon that original version and is maintained independently under MIT.

See [PRIVACY.md](./docs/PRIVACY.md) for local storage, optional SSH collection, and release data boundaries.

---

## 中文

### 适用范围

本仓库包含一个本地优先的桌面工具，通过读取本机 Codex 认证状态显示额度并切换当前账号。

涉及安全的部分包括令牌刷新与额度请求、账号切换与当前会话替换、Desktop 重启辅助流程、Windows Desktop 会话备份和恢复，以及截图、文档和示例数据的仓库隐私管理。

### 报告漏洞

不得在公开 Issue 中包含以下信息：

- 访问令牌、刷新令牌或 `auth.json` 内容。
- 正在使用的额度、账号快照或 Desktop 会话快照。
- 私人文件路径或暴露真实账号的截图。

如果本仓库已启用 GitHub 私密安全报告，请使用该渠道。如不可用，请仅提交不含敏感内容的简短公开 Issue，并说明可以私下提供详情。安排私密沟通时也不要公开凭据。

### 仓库规则

- 不得提交真实 `auth.json`、正在使用的账号快照或 Desktop 会话备份。
- 不得提交包含真实账号身份的截图。
- 文档与界面素材使用合成示例。
- 完整英文和中文的安全、隐私说明必须保持一致。
- 保留原作者 [Adem Isler 的 CodexControl](https://github.com/ademisler/codexcontrol) 及第三方作者所需的版权归属。本项目在该初版基础上改进，遵循 MIT 许可证独立维护。

本地存储、可选 SSH 采集及公开发布的数据边界见 [PRIVACY.md](./docs/PRIVACY.md)。
