# Cross-platform release process · 双平台发布流程

[English](#english) · [中文](#中文)

## English

macOS and Windows are two implementations of the same project. Put each platform's attachments in the same GitHub Release, and separately state its version, architecture, signing status, and completed validation. Use [this repository's Releases](https://github.com/ZeusLiu666/codexcontrol/releases), rather than an upstream repository, personal website, or personal Homebrew tap.

### Version and release record

1. Choose the project version and update the corresponding app version, package version, and `CHANGELOG.md`.
2. Review source, documentation, commit-author metadata, and every attachment for the publisher's private information.
3. Complete the relevant platform's build and validation, then tag the verified commit and create a Release, or add the other platform's attachments to an existing Release of the same version.
4. Claim only the validation actually completed on each platform. Existing macOS assets may be retained; Windows validation does not establish that a new macOS build was tested.

### Windows build

Use Windows x64, Python 3.12 x64, and the official Inno Setup 6.5.3 compiler. The script verifies the compiler hash. From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
powershell -ExecutionPolicy Bypass -File .\windows\package_release.ps1 `
  -Python .\.venv\Scripts\python.exe -Version 1.2.9 -Clean
```

Replace the example version with the release version. Pass `-InnoSetupCompiler <path-to-ISCC.exe>` when needed. Outputs are written to `ReleaseArtifacts`:

| Attachment | Purpose |
| --- | --- |
| `CodexControl-<version>-windows-x64-Setup.exe` | Per-user installer, Start Menu entry, and optional sign-in startup |
| `CodexControl-<version>-windows-x64-portable.zip` | Standalone executable, documentation, and licenses |
| `SHA256SUMS-windows.txt` | SHA-256 checksums for Windows downloads |

Use temporary directories or an isolated test user and synthetic accounts for installer, portable-package, and uninstall validation. Check startup, the main window, tray, exit, installed files, shortcuts, and uninstallation. Preserving user data on uninstall is expected; the test environment is responsible for clearing its own disposable data. Explicitly state when real sign-in has not been tested.

### macOS build and existing assets

The macOS arm64 `.dmg` / `.pkg` assets in an existing Release are separate platform builds. Preserve their descriptions, checksums, and validation scope. Adding Windows attachments alone does not imply that macOS was rebuilt or retested.

Building from source requires macOS 14 or later and the Swift 6.1 toolchain:

```bash
swift build
swift test
./Scripts/package_app.sh
./Scripts/build_release_artifacts.sh
```

The scripts generate `ReleaseArtifacts/CodexControl-macos.zip` and its `.sha256` file. This archive script recreates `ReleaseArtifacts`; build in an isolated checkout or preserve other platforms' completed assets first. Verify DMG/PKG creation and signing separately from this ZIP command.

With `CODE_SIGN_IDENTITY` and `NOTARY_KEYCHAIN_PROFILE`, the script can sign, notarize, and staple the app. Without those credentials, do not describe the build as Developer ID-signed or notarized. Before release, check app startup, the menu bar, account operations, and optional widgets on the target architecture. Signing and notarization credentials belong only in secure local configuration or repository Secrets.

### GitHub publication

Put Windows installers, the Windows portable archive, macOS assets, and their checksums in the same version's Release in this repository. Document supported systems and architectures, upgrade/data-retention behavior, and each platform's validation scope.

`.github/workflows/release.yml` is the tag-triggered release entry point. Before enabling it, confirm that it targets the current repository, builds the correct filenames, and obtains signing/publication credentials from appropriately scoped Secrets. Do not reuse another maintainer's repository target or private deployment credentials. Alternatively, prepare a draft Release with reviewed local builds, verify it, and publish it.

For a Windows-only update, `.github/workflows/windows-release.yml` runs when the Windows `__version__` changes on `main`, or by manual dispatch from `main`. Add reviewed bilingual notes at `docs/releases/v<version>-windows.md`. It tests and builds that exact commit, verifies the three Windows attachments, creates a draft `v<version>-zeusliu.1` Release, and publishes it as a prerelease only after uploaded checksums match. It refuses to overwrite an already published version. This path leaves existing macOS downloads in their original Release.

Deploying the website is not required to publish installers. Deploy only when you own the destination and have configured permission to deploy there. Do not describe the upstream domain as belonging to this repository.

### Privacy checks before release

Ignore rules are only a supporting measure; tracked files can still be committed. Before uploading, review the complete publication tree, Git metadata, images, build logs, and final binaries:

- No real emails, account IDs, tokens, private usernames, hosts, SSH ports, key paths, or personal absolute paths.
- No `auth.json`, live account lists, quota snapshots, Token ledgers, full sessions, auth backups, SSH configuration, or Desktop caches.
- No `.env`, private keys, browser state, personal certificates, signing passwords, or deployment credentials.
- Screenshots contain only clearly synthetic examples; exclude images whose origin cannot be verified.
- Packages contain only explicitly allowed programs, dependencies, documentation, and licenses; never recursively package a developer workspace or user-data directory.
- Python bytecode, PyInstaller archives, debug data, and compressed attachments contain no personal build paths.
- Keep `LICENSE` and required third-party notices. Mandatory copyright attribution is not the publisher's private data and must be retained.

After review, recalculate final attachment hashes and upload the checksums alongside the files. See [PRIVACY.md](./PRIVACY.md) for the data boundary.

---

## 中文

macOS 和 Windows 是同一项目的两个系统实现。在同一 GitHub Release 中上传两个系统各自的附件，并在说明中分别列出版本、架构、签名状态及实际完成的测试。下载入口使用[当前仓库的 Releases](https://github.com/ZeusLiu666/codexcontrol/releases)，不依赖上游仓库、个人网站或个人 Homebrew tap。

### 版本与发布记录

1. 选择项目版本号，并同步相应应用版本、打包版本及 `CHANGELOG.md`。
2. 审查源码、文档、提交作者元数据和待上传附件，确认不包含发布者私人信息。
3. 完成相应系统的构建和验证，再为已验证提交创建版本标签及 Release，或将另一个系统的附件补入同版本已有 Release。
4. 每个平台只声明实际验证过的结果；已有的 macOS 资产可以保留，但不能将 Windows 上的验证写成新 macOS 构建已经通过。

### Windows 构建

要求 Windows x64、Python 3.12 x64 和官方 Inno Setup 6.5.3。脚本会核对编译器哈希。在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
powershell -ExecutionPolicy Bypass -File .\windows\package_release.ps1 `
  -Python .\.venv\Scripts\python.exe -Version 1.2.9 -Clean
```

示例版本应替换为当前发布版本。必要时传入 `-InnoSetupCompiler <ISCC.exe路径>`。产物位于 `ReleaseArtifacts`：

| 附件 | 用途 |
| --- | --- |
| `CodexControl-<版本>-windows-x64-Setup.exe` | 当前用户安装程序，开始菜单入口及可选登录后自动启动 |
| `CodexControl-<版本>-windows-x64-portable.zip` | 解压运行的独立程序与许可证、说明 |
| `SHA256SUMS-windows.txt` | Windows 附件的 SHA-256 校验值 |

安装、便携包及卸载验证应使用临时目录或隔离的测试用户环境，并使用合成账号。检查启动后的主窗口、系统托盘、退出、安装目录、快捷方式和卸载结果。卸载保留用户数据是预期行为，测试数据由测试环境负责清理。没有真实登录验证时，应明确写出这一限制。

### macOS 构建与已有附件

已有 Release 中的 macOS arm64 `.dmg` / `.pkg` 是独立系统产物。保留其既有说明、校验文件与验证范围，不因补充 Windows 附件而声称已经重新构建或验证。

从源码构建要求 macOS 14 及以上与 Swift 6.1 工具链：

```bash
swift build
swift test
./Scripts/package_app.sh
./Scripts/build_release_artifacts.sh
```

源码脚本生成 `ReleaseArtifacts/CodexControl-macos.zip` 及同名 `.sha256` 文件。该脚本会重建 `ReleaseArtifacts`，请在独立工作目录中构建，或预先保存其他平台已生成的发布附件。此 ZIP 构建命令与现有 DMG / PKG 的制作、签名流程应分别核验。

配置 `CODE_SIGN_IDENTITY` 和 `NOTARY_KEYCHAIN_PROFILE` 后，脚本可以执行签名、公证和装订。未提供凭据时不得将产物描述为开发者签名或已公证。发布前在目标架构系统上检查应用启动、菜单栏、账号操作和可选桌面组件；签名、公证凭据只能存储在本机安全配置或仓库 Secrets 中。

### GitHub 发布

将 Windows 安装包、Windows 便携包、macOS 附件和各自校验文件放在本仓库同一版本 Release 下。描述中应说明支持的系统版本、架构、升级与数据保留行为，以及每个平台的测试范围。

`.github/workflows/release.yml` 是标签触发的发布入口。启用之前确认它使用当前仓库上下文、构建正确的文件名，并且所有签名与发布凭据均来自适当权限的 Secrets；不要沿用他人的仓库目标或个人部署凭据。也可以先创建草稿 Release，上传经审查的本地构建附件，核对后发布。

仅更新 Windows 时，修改 `main` 上的 Windows `__version__` 会触发 `.github/workflows/windows-release.yml`，也可以从 `main` 手动启动。请先在 `docs/releases/v<版本>-windows.md` 中准备中英文说明。流程测试并构建该次提交，校验三个 Windows 附件，创建 `v<版本>-zeusliu.1` 草稿 Release，上传后的哈希一致才发布为预发布版；已公开的版本不会被覆盖。此流程保留原 Release 中的 macOS 下载。

网站源码和网站部署不属于安装包发布的必要步骤。只有拥有目标站点及明确配置的部署权限时才部署；不要在项目介绍中把上游域名描述为本仓库拥有。

### 发布前隐私检查

忽略规则只是辅助措施，已经被 Git 跟踪的文件仍可能被提交。上传前检查整个待发布树、Git 提交元数据、图片、构建日志及最终二进制：

- 没有真实邮箱、账号 ID、令牌、私人用户名、主机名、SSH 端口、密钥路径或个人绝对路径。
- 没有 `auth.json`、账号清单、额度快照、Token 账本、完整会话、认证备份、SSH 配置或 Desktop 会话缓存。
- 没有 `.env`、私钥、浏览器状态、个人证书、签名密码或部署凭据。
- 截图仅含明确合成的示例信息；无法确认来源的截图不发布。
- 安装包只包含允许发布的程序、依赖、说明与许可证，不递归打包开发目录或用户数据。
- Python 编译文件、PyInstaller 归档、调试信息和压缩附件也没有嵌入构建机器的个人路径。
- 保留 `LICENSE` 和必要第三方授权声明。已有开源作者的版权署名属于必须保留的授权归属，不能当作发布者的私人数据删除。

完成检查后重新计算最终附件哈希，并将校验文件与附件一起上传。详细的数据范围见 [PRIVACY.md](./PRIVACY.md)。
