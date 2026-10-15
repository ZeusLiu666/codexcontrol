# Contributing · 贡献指南

[English](#english) · [中文](#中文)

## English

This project is based on and improved from the original [CodexControl by Adem Isler](https://github.com/ademisler/codexcontrol). It is an independently maintained derivative under the MIT License. Preserve the original and third-party copyright notices when contributing.

### Development setup

macOS:

```bash
swift build
./Scripts/package_app.sh
open ./Build/CodexControl.app
```

Windows, in an isolated development environment:

```powershell
python -m pip install -r .\windows\requirements-build.txt
python .\windows\CodexControlWindows.pyw
$env:PYTHONPATH = "windows"
python -m unittest discover -s windows/tests -v
```

The static website lives in `site/`. Only deploy with `./Scripts/deploy_site.sh` when you own the destination and have explicitly configured deployment access. An upstream domain is not a deployment destination owned by this repository.

For macOS release archives, use `./Scripts/build_release_artifacts.sh`. For Windows installers and portable packages, use `windows/package_release.ps1`. See the complete [release process](./docs/releasing.md) for dependencies, metadata cleanup, and validation.

### Pull request guidance

- Keep changes focused and reviewable.
- Do not commit real account data, `auth.json`, snapshots, or screenshots containing real identities.
- Use synthetic data for UI assets, tests, and documentation.
- Reuse the logo and mark assets in [`site/assets`](./site/assets) instead of creating unrelated variants.
- For quota changes, describe the exact scenario you validated.
- For account-switching changes, describe expected Desktop restart behavior and platform-specific global-state/session-cache handling.
- Keep the complete English and Chinese documentation in sync. Use English first, followed by the full Chinese version. Keep code, commands, and filenames executable and unchanged by translation.

### Before opening a pull request

- Build the macOS app when changing its implementation.
- Run Windows tests in an isolated environment when changing the Windows implementation.
- Regenerate affected release attachments when changing packaging or bundled documentation.
- Review source and artifacts for personal absolute paths, real emails, tokens, and live Desktop session snapshots.
- Preserve upstream attribution and required license terms. Read [SECURITY.md](./SECURITY.md) before reporting a security issue.

---

## 中文

本项目基于原作者 [Adem Isler 的 CodexControl 初版](https://github.com/ademisler/codexcontrol)改进而来，是遵循 MIT 许可证、独立维护的衍生版本。贡献时请保留原作者与第三方所需的版权声明。

### 开发环境

macOS：

```bash
swift build
./Scripts/package_app.sh
open ./Build/CodexControl.app
```

Windows，请在隔离的开发环境中运行：

```powershell
python -m pip install -r .\windows\requirements-build.txt
python .\windows\CodexControlWindows.pyw
$env:PYTHONPATH = "windows"
python -m unittest discover -s windows/tests -v
```

静态网站位于 `site/`。只有拥有目标站点并明确配置部署权限时，才使用 `./Scripts/deploy_site.sh` 部署。上游域名不是本仓库拥有的部署目标。

macOS 发布归档使用 `./Scripts/build_release_artifacts.sh`；Windows 安装包与便携包使用 `windows/package_release.ps1`。依赖、元数据清理与验证要求见完整[发布流程](./docs/releasing.md)。

### Pull Request 要求

- 保持修改集中，方便审查。
- 不得提交真实账号、`auth.json`、快照或显示真实身份的截图。
- 界面素材、测试与文档使用合成数据。
- 复用 [`site/assets`](./site/assets) 中的标志素材，不另建无关变体。
- 修改额度逻辑时，说明实际验证的具体场景。
- 修改账号切换逻辑时，说明预期 Desktop 重启行为，以及各平台全局状态和会话缓存的处理方式。
- 完整英文和中文文档保持同步，英文在前、完整中文在后。代码、命令和文件名不因翻译而失去可执行性或发生改名。

### 提交 Pull Request 前

- 修改 macOS 实现时，完成该应用构建。
- 修改 Windows 实现时，在隔离环境中运行测试。
- 修改打包或随包文档时，重新生成受影响的发布附件。
- 检查源码和产物，排除个人绝对路径、真实邮箱、令牌和正在使用的 Desktop 会话快照。
- 保留上游归属与必要许可证条款。报告安全问题前请阅读 [SECURITY.md](./SECURITY.md)。
