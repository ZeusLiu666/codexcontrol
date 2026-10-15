# CodexControl

<p align="center">
  <img src="./site/assets/codexcontrol-mark.svg" alt="CodexControl logo" width="72">
</p>

**在 macOS 和 Windows 上查看 Codex 额度、管理本地账号并切换当前登录。**

Local-first Codex quota tracking and account switching for macOS and Windows.

CodexControl 的两个系统版本在同一个仓库中维护，共用项目介绍、隐私说明与发布记录。macOS 使用 SwiftUI / AppKit，Windows 使用 Python / Tkinter 与系统托盘；两个版本的界面和系统集成有所不同。此项目是独立工具，与 OpenAI 无隶属关系。

[下载与发布记录](https://github.com/ZeusLiu666/codexcontrol/releases) · [Windows 使用说明](./windows/README.md) · [隐私说明](./docs/PRIVACY.md) · [发布流程](./docs/releasing.md) · [MIT 许可证](./LICENSE)

## 下载与安装

在本仓库的 [Releases](https://github.com/ZeusLiu666/codexcontrol/releases) 中按系统选择附件。预发布版本也列在此页面中；架构、签名状态与测试范围以对应 Release 说明为准。

| 系统 | 发布附件 | 安装方式 |
| --- | --- | --- |
| Windows 10 x64 1809 / Windows 11 x64 | `CodexControl-<版本>-windows-x64-Setup.exe` | 运行安装程序，按当前用户安装；可选择开机登录后启动 |
| Windows 10 x64 1809 / Windows 11 x64 | `CodexControl-<版本>-windows-x64-portable.zip` | 解压后运行 `CodexControl.exe`，无需另装 Python |
| macOS 14 及以上，Apple Silicon | 现有 macOS arm64 `.dmg` / `.pkg` | 打开磁盘映像或安装程序，按附件说明安装 |

Windows 安装包和便携包运行的是同一程序。便携包仍将账号和运行数据保存在当前用户的 `%APPDATA%\CodexControl` 中，不会把账号保存在压缩包内。安装程序卸载时保留这些用户数据。Windows 发布附件提供 SHA-256 校验值。

使用添加账号、重新登录等功能需要本机可用的 Codex CLI。额度查询和登录需要网络连接。账号切换可能关闭并重新启动 Codex Desktop，请先保存工作。

## 功能

| 功能 | macOS | Windows |
| --- | --- | --- |
| 读取账号实时额度和重置时间 | 支持 | 支持 |
| 分别显示 5 小时、7 天额度窗口 | 接口提供时显示 | 接口提供时显示 |
| 添加账号、重新登录、刷新、移除与打开账号目录 | 支持 | 支持 |
| 切换本机 Codex 当前账号 | 支持 | 支持，并处理 Windows Desktop 会话状态 |
| 本地 Token 增量统计与近 7 天视图 | 支持 | 支持 |
| 用户主动配置的 SSH Token 统计 | 支持，默认关闭 | 支持，默认关闭 |
| 桌面入口 | 菜单栏与 macOS Widget | 系统托盘与主窗口 |

额度从 OpenAI 接口读取，受账号套餐、权限、网络与接口可用性影响。接口没有返回的额度窗口不会被推算为可用额度。账号自动刷新间隔为 5 分钟，Token 统计在程序运行时约每 30 秒检查一次。

## 工作方式

程序读取本地 Codex 账号的 `auth.json`，在需要时刷新登录凭据，并向 OpenAI 请求额度。切换账号会更新本机 `~/.codex` 中的登录状态；Windows 版还会保存和恢复对应账号的 Codex Desktop 会话缓存、同步全局状态并按需重启 Desktop。

Token 统计从本地 Codex 会话事件中提取输入、缓存输入、输出、推理及总 Token 数。首次运行为已有本地日志建立基线，随后只统计新增完整事件；它不是对全部历史账单的回溯，也不提供费用结算。账号归属依赖本地登录状态及程序执行的切换，直接在其他工具中更换账号可能影响归属。

### 可选远程统计

两个版本默认都不会连接 SSH 主机。远程统计由使用者主动配置，两个平台的配置入口不同：

- Windows：为程序进程设置 `CODEXCONTROL_SSH_HOSTS`，多个目标用英文逗号分隔。
- macOS：在 `~/Library/Application Support/CodexControl/remote-hosts.json` 中配置目标；该文件在刷新时重新读取。

Windows 示例：

```powershell
# 当前 PowerShell 会话启动的程序使用此设置
$env:CODEXCONTROL_SSH_HOSTS = "build-server,compute-node"
.\CodexControl.exe
```

macOS 配置文件示例：

```json
[
  { "host": "build-server", "isOptional": true },
  { "host": "compute-node", "isOptional": true }
]
```

macOS 中 `host` 和 `isOptional` 字段都需要提供；主机别名仅使用字母、数字、点、连字符或下划线，SSH 用户、端口与密钥在 `~/.ssh/config` 中配置。缺少文件、格式错误或含非法目标时不启用远程采集；使用空数组 `[]` 可停用全部目标。

示例名称仅为占位符。请自行在 `~/.ssh/config` 中配置可访问的 SSH 别名，并使用非交互式 SSH 认证；远端需要 `python3`。采集器通过 SSH 读取远端 Codex Token 事件、账号标识及读取进度，只向本地返回统计所需字段，不复制完整对话或远端认证文件。首次远程采集读取最近 7 天的相关事件，后续使用检查点增量读取。

停用所配置的远程目标并重新启动程序即可关闭连接；已有本地统计缓存仍会保留。不要将自己的 SSH 配置、主机名、密钥或远程统计缓存提交到仓库。

## 隐私与本地数据

发布包只包含程序、必要依赖、许可证和说明，不包含发布者的账号、认证文件、对话日志、SSH 配置或本机缓存。仓库中的测试应仅使用合成数据。

运行后，程序会在你的电脑上创建包含敏感信息的账号与会话数据：

| 系统 | 应用数据目录 |
| --- | --- |
| macOS | `~/Library/Application Support/CodexControl` |
| Windows | `%APPDATA%\CodexControl` |

**本地优先不等于加密存储。** 账号元数据、`auth.json`、认证备份和 Desktop 会话缓存可能包含邮箱、账号 ID、有效令牌或登录会话；程序没有为这些文件提供统一的额外加密保证。请保护系统账号和磁盘，不要把应用数据目录或 `~/.codex` 上传到 GitHub、网盘公开目录或问题附件。详细的数据流、清理和发布检查见[隐私说明](./docs/PRIVACY.md)。

## 从源码运行与构建

### Windows

建议使用 Windows x64 和 Python 3.12，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements.txt
.\.venv\Scripts\python.exe .\windows\CodexControlWindows.pyw
```

构建独立可执行程序：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build.ps1 `
  -Python .\.venv\Scripts\python.exe -InstallDependencies -Clean
```

安装包、便携包、测试命令与构建选项见[Windows 说明](./windows/README.md)。

### macOS

需要 macOS 14 及以上、Swift 6.1 工具链及相应开发工具：

```bash
swift build
swift test
./Scripts/package_app.sh
open ./Build/CodexControl.app
```

macOS 打包、可选签名与公证说明见[发布流程](./docs/releasing.md)。Windows 构建成功不代表 macOS 构建已经验证，发布说明应分别记录两个系统的测试结果。

## 仓库结构

```text
Sources/CodexControl/        macOS 主程序
Sources/CodexControlWidget/  macOS 桌面组件
Tests/                      macOS 测试
Scripts/                    macOS 构建与打包脚本
Support/                    应用元数据
windows/                    Windows 主程序、测试与安装包脚本
docs/                       共用隐私与发布文档
site/                       静态网站源码
LICENSE                     上游 MIT 版权与授权声明
NOTICE                      其他归属说明
```

`site/` 中的网页源码不代表本仓库已拥有或部署任何同名域名。下载来源以本仓库 Releases 为准。

## 授权与贡献

项目使用 [MIT 许可证](./LICENSE)，保留原始 CodexControl 的上游版权与授权声明。macOS 与 Windows 版本均属于同一项目的系统实现。贡献前请阅读 [CONTRIBUTING.md](./CONTRIBUTING.md)，安全问题处理说明见 [SECURITY.md](./SECURITY.md)。提交代码、日志或截图前请移除真实账号、令牌、设备路径及私人主机信息。
