# CodexControl 统一发布流程

macOS 和 Windows 是同一项目的两个系统实现。在同一 GitHub Release 中上传两个系统各自的附件，并在说明中分别列出版本、架构、签名状态及实际完成的测试。下载入口使用[当前仓库的 Releases](https://github.com/ZeusLiu666/codexcontrol/releases)，不依赖上游仓库、个人网站或个人 Homebrew tap。

## 版本与发布记录

1. 选择项目版本号，并同步相应应用版本、打包版本及 `CHANGELOG.md`。
2. 审查源码、文档、提交作者元数据和待上传附件，确认不包含发布者私人信息。
3. 完成相应系统的构建和验证，再为已验证提交创建版本标签及 Release，或将另一个系统的附件补入同版本已有 Release。
4. 每个平台只声明实际验证过的结果；已有的 macOS 资产可以保留，但不能将 Windows 上的验证写成新 macOS 构建已经通过。

## Windows 构建

要求 Windows x64、Python 3.12 x64 和官方 Inno Setup 6.5.3。脚本会核对编译器哈希。在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
powershell -ExecutionPolicy Bypass -File .\windows\package_release.ps1 `
  -Python .\.venv\Scripts\python.exe -Version 1.2.8 -Clean
```

示例版本应替换为当前发布版本。必要时传入 `-InnoSetupCompiler <ISCC.exe路径>`。产物位于 `ReleaseArtifacts`：

| 附件 | 用途 |
| --- | --- |
| `CodexControl-<版本>-windows-x64-Setup.exe` | 当前用户安装程序，开始菜单入口及可选登录后自动启动 |
| `CodexControl-<版本>-windows-x64-portable.zip` | 解压运行的独立程序与许可证、说明 |
| `SHA256SUMS-windows.txt` | Windows 附件的 SHA-256 校验值 |

安装、便携包及卸载验证应使用临时目录或隔离的测试用户环境，并使用合成账号。检查启动后的主窗口、系统托盘、退出、安装目录、快捷方式和卸载结果。卸载保留用户数据是预期行为，测试数据由测试环境负责清理。没有真实登录验证时，应明确写出这一限制。

## macOS 构建与已有附件

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

## GitHub 发布

将 Windows 安装包、Windows 便携包、macOS 附件和各自校验文件放在本仓库同一版本 Release 下。描述中应说明支持的系统版本、架构、升级与数据保留行为，以及每个平台的测试范围。

`.github/workflows/release.yml` 是标签触发的发布入口。启用之前确认它使用当前仓库上下文、构建正确的文件名，并且所有签名与发布凭据均来自适当权限的 Secrets；不要沿用他人的仓库目标或个人部署凭据。也可以先创建草稿 Release，上传经审查的本地构建附件，核对后发布。

网站源码和网站部署不属于安装包发布的必要步骤。只有拥有目标站点及明确配置的部署权限时才部署；不要在项目介绍中把上游域名描述为本仓库拥有。

## 发布前隐私检查

忽略规则只是辅助措施，已经被 Git 跟踪的文件仍可能被提交。上传前检查整个待发布树、Git 提交元数据、图片、构建日志及最终二进制：

- 没有真实邮箱、账号 ID、令牌、私人用户名、主机名、SSH 端口、密钥路径或个人绝对路径。
- 没有 `auth.json`、账号清单、额度快照、Token 账本、完整会话、认证备份、SSH 配置或 Desktop 会话缓存。
- 没有 `.env`、私钥、浏览器状态、个人证书、签名密码或部署凭据。
- 截图仅含明确合成的示例信息；无法确认来源的截图不发布。
- 安装包只包含允许发布的程序、依赖、说明与许可证，不递归打包开发目录或用户数据。
- Python 编译文件、PyInstaller 归档、调试信息和压缩附件也没有嵌入构建机器的个人路径。
- 保留 `LICENSE` 和必要第三方授权声明。已有开源作者的版权署名属于必须保留的授权归属，不能当作发布者的私人数据删除。

完成检查后重新计算最终附件哈希，并将校验文件与附件一起上传。详细的数据范围见 [PRIVACY.md](./PRIVACY.md)。
