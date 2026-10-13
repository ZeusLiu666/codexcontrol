# CodexControl 1.2.8

Updated by ZeusLiu

## English

A macOS menu-bar app for Codex accounts and usage, based on [CodexControl by Adem Isler](https://github.com/ademisler/codexcontrol), under the MIT License. Updated by **ZeusLiu**.

### Download and install

Requires **Apple Silicon (M1 or newer) and macOS 14 or later**. Version **1.2.8, build 17** updates the bundled wording and release metadata; app features are unchanged from build 16.

1. Download `CodexControl-1.2.8-macos-arm64.dmg` from this repository’s Releases.
2. Quit CodexControl, open the disk image, and drag `CodexControl.app` into `Applications`.
3. Launch it from Applications and click its menu-bar icon.

You can also use `CodexControl-1.2.8-macos-arm64.pkg` from the same Release. Both install the same app; choose either one. Download checksums are in `SHA256SUMS.txt`.

The app is ad-hoc signed and has not been notarized by Apple. macOS may show a verification warning.

### Features

- Hover over a daily usage square to see its full date and exact token counts. Click to pin the details; close them with the close button or Escape.
- View input, cached input, output, and reasoning counts, with their inclusion relationships made clear.
- Clearer menu-bar cards, remaining limits, reset times, status messages, and refresh feedback.
- Account switching, usage tracking, and desktop widgets.
- Optional remote usage collection, disabled until you configure it locally.

### Local data

The downloads contain no personal accounts, authentication tokens, SSH keys or configuration, server addresses, usage history, session logs, or personal account screenshots. The app uses data on the computer where it runs. For compatibility, it keeps using `~/Library/Application Support/CodexControl`, so existing local accounts may appear when you launch it.

### Optional remote usage

To enable remote collection, create `~/Library/Application Support/CodexControl/remote-hosts.json` on your computer:

```json
[
  { "host": "codex-server", "isOptional": false },
  { "host": "optional-server", "isOptional": true }
]
```

Replace these examples with your own `~/.ssh/config` aliases and set up non-interactive SSH authentication first. Keep your actual configuration and credentials local. The app does not store SSH passwords or collect remote usage without this configuration.

### Build from source

Download **`CodexControl-1.2.8-source-sanitized.zip`** from the Release assets, extract it, and open the `CodexControl` folder. This is the app’s source archive. GitHub’s automatically generated **Source code (zip/tar.gz)** downloads contain only this distribution repository’s documentation, not the app source.

You will need Swift 6.1 or later and the macOS development tools:

```sh
swift test
./Scripts/package_app.sh
./Scripts/build_installers.sh
```

`package_app.sh` builds the app and widget and bundles the complete LICENSE and NOTICE. It uses ad-hoc signing by default; set `CODE_SIGN_IDENTITY` to use your own Developer ID Application certificate. Installers are written to `ReleaseArtifacts`, which is excluded from the source archive.

The app previously passed all 18 tests. Build 17 changes only documentation and release metadata; those tests were not rerun for this update.

### Credits and license

Original author: **Adem Isler** — [ademisler/codexcontrol](https://github.com/ademisler/codexcontrol)

**Updated by ZeusLiu**

Released under the [MIT License](LICENSE). See [NOTICE](NOTICE) for attribution. This release is maintained by ZeusLiu independently of the original author.

---

## 中文

用于管理 Codex 账户和查看用量的 macOS 菜单栏应用，基于 [Adem Isler 的 CodexControl](https://github.com/ademisler/codexcontrol)，遵循 MIT 许可证。由 **ZeusLiu** 更新。

### 下载与安装

需要 **Apple Silicon（M1 或更新芯片）和 macOS 14 或更新版本**。当前版本为 **1.2.8，构建 17**，本次更新随包文案与发布元数据，应用功能与构建 16 相同。

1. 从本仓库 Releases 下载 `CodexControl-1.2.8-macos-arm64.dmg`。
2. 退出 CodexControl，打开磁盘映像，将 `CodexControl.app` 拖入 `Applications`。
3. 从“应用程序”启动，点击菜单栏图标打开面板。

也可选择同一 Release 中的 `CodexControl-1.2.8-macos-arm64.pkg` 标准安装器。两者安装的是同一个应用，任选一种即可。下载文件的校验值见 `SHA256SUMS.txt`。

应用使用本地临时签名（ad-hoc），尚未经过 Apple 公证，macOS 可能显示验证提示。

### 功能

- 悬停在每日用量方格上，可查看完整日期和精确 token 数量；点击固定详情，使用关闭按钮或 Escape 收起。
- 查看输入、缓存输入、输出和推理数量，并了解各项的包含关系。
- 改善菜单栏卡片、剩余额度、重置时间、状态消息和刷新反馈。
- 支持账户切换、用量统计和桌面小组件。
- 支持可选远程用量采集，默认关闭，需在本机配置后启用。

### 本机数据

下载内容不包含个人账户、登录 token、SSH 密钥或配置、服务器地址、用量历史、会话日志或真实账户截图。应用读取运行它的电脑上的数据，并为兼容已有版本继续使用 `~/Library/Application Support/CodexControl`，因此启动后可能显示本机已有的账户。

### 可选远程用量

如需启用远程采集，请在本机创建 `~/Library/Application Support/CodexControl/remote-hosts.json`：

```json
[
  { "host": "codex-server", "isOptional": false },
  { "host": "optional-server", "isOptional": true }
]
```

请将示例名称替换为自己的 `~/.ssh/config` 别名，并提前配置非交互式 SSH 身份验证。实际配置与凭据请保留在本机。应用不保存 SSH 密码；未提供此配置时，不采集远程用量。

### 从源码构建

请从 Release 附件下载 **`CodexControl-1.2.8-source-sanitized.zip`**，解压后进入 `CodexControl` 文件夹。这份手动上传的附件包含应用源码；GitHub 自动生成的 **Source code (zip/tar.gz)** 仅包含本分发仓库的文档，不包含应用源码。

需要 Swift 6.1 或更新版本及 macOS 开发工具：

```sh
swift test
./Scripts/package_app.sh
./Scripts/build_installers.sh
```

`package_app.sh` 会构建应用和小组件，并随包附上完整 LICENSE 与 NOTICE。默认使用本地临时签名；设置 `CODE_SIGN_IDENTITY` 可使用自己的 Developer ID Application 证书。安装包输出到 `ReleaseArtifacts`，源码归档不包含该目录。

应用此前已通过全部 18 项测试。构建 17 仅更新文档和发布元数据，本次更新未重新运行这些测试。

### 署名与许可

原作者：**Adem Isler** — [ademisler/codexcontrol](https://github.com/ademisler/codexcontrol)

**由 ZeusLiu 更新**

遵循 [MIT 许可证](LICENSE)，详细归属见 [NOTICE](NOTICE)。本次发布由 ZeusLiu 独立维护。
