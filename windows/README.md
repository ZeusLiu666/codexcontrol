# CodexControl for Windows

[English](#english) · [中文](#中文)

## English

**Based on and improved from the original CodexControl by [Adem Isler](https://github.com/ademisler/codexcontrol).** This Windows implementation shares the project name, release history, and privacy commitments with the macOS implementation in this repository. This edition is maintained independently of the original author; the original MIT copyright notices are retained.

CodexControl provides local account switching, live quota tracking, and Token statistics.

[Project overview and downloads](https://github.com/ZeusLiu666/codexcontrol#readme) · [Privacy](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md) · [Unified release process](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/releasing.md)

### Requirements

- Windows 10 x64 1809 (build 17763) or later, or Windows 11 x64.
- The installer and portable package do not require a separate Python installation.
- Adding accounts and signing in again require an available Codex CLI. Quota retrieval and sign-in require network access.
- Optional SSH statistics require a local OpenSSH client, non-interactive authentication configured by the user, and `python3` on the remote host.

### Installation and use

Download and run `CodexControl-<version>-windows-x64-Setup.exe` from this repository's Releases. It installs for the current user at `%LOCALAPPDATA%\Programs\CodexControl` and creates a Start menu shortcut. Start at sign-in is optional and unchecked by default.

Alternatively, download `CodexControl-<version>-windows-x64-portable.zip`, extract it, and run `CodexControl.exe`. The portable package contains no preconfigured accounts and still stores runtime data at `%APPDATA%\CodexControl`.

The app provides a system tray and account window for adding, refreshing, signing in again, switching, and removing accounts, and opening account folders. When supplied by the quota API, it shows separate 5-hour and 7-day windows with reset times. Local Token statistics count new events after the first run and show a 7-day summary. SSH statistics are disabled by default; configuration is described in the [main README](https://github.com/ZeusLiu666/codexcontrol#readme).

Switching accounts updates `~/.codex/auth.json`, synchronizes Codex global state, and saves and restores the corresponding account's Desktop session cache. Switching may close and restart Codex Desktop, so save your work first. Desktop cache layouts may change between versions; related compatibility logic and tests are included in this directory's source code.

Uninstalling removes the program and shortcuts but retains accounts and runtime data in `%APPDATA%\CodexControl`. This directory may contain valid authentication tokens and sessions. See the [privacy guide](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md) for cleanup instructions.

### Run from source

Python 3.12 x64 is recommended. Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements.txt
.\.venv\Scripts\python.exe .\windows\CodexControlWindows.pyw
```

Running from source also uses the current user's application data directory. Use temporary user directories and synthetic accounts for tests and UI checks to avoid touching real sign-in state.

### Build a standalone EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build.ps1 `
  -Python .\.venv\Scripts\python.exe -InstallDependencies -Clean
```

The output is `windows\dist\CodexControl.exe`. Use `-Python <path-to-python.exe>` to select Python and `-Version <version>` to set the file version. `-InstallDependencies` installs the pinned build dependencies from `requirements-build.txt`; omit it if those dependencies are already installed.

### Build the installer and portable package

The official Inno Setup 6.5.3 compiler is required. The script checks its hash. Replace the sample version with the version you are releasing:

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\package_release.ps1 `
  -Python .\.venv\Scripts\python.exe -Version 1.2.8 -InstallDependencies -Clean
```

If the script cannot find the compiler automatically, pass `-InnoSetupCompiler <path-to-ISCC.exe>`. It also accepts `-Python <path-to-python.exe>`. Outputs are written to `ReleaseArtifacts`:

- `CodexControl-<version>-windows-x64-Setup.exe`
- `CodexControl-<version>-windows-x64-portable.zip`
- `SHA256SUMS-windows.txt`

The portable package's `install.ps1` can copy the app to the current user's programs directory. Read its parameters before running it. This example keeps start at sign-in disabled:

```powershell
# Run from the extracted directory; explicitly disable start at sign-in.
& .\install.ps1 `
  -SourceExe .\CodexControl.exe -EnableStartup:$false -Launch
```

### Tests

Run from the repository root in an isolated environment. The tests also cover release tooling, so the build dependencies are required:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
```

Before release, also verify installation, launch, the system tray, uninstallation, portable launch, and archive contents. Check that the final EXE, installer, and archives contain no publisher-specific local paths or private data. Do not switch real accounts in automated smoke tests.

### Local data and privacy

`%APPDATA%\CodexControl` may contain account information, authentication backups, managed account directories, quota snapshots, Token statistics, and copies of Desktop sessions. These files are not guaranteed to have additional encryption and must not be included in bug reports or uploaded with source code. Release scripts should package only explicitly listed program and documentation files, never the application data directory. See [PRIVACY.md](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md) for the full policy.

## 中文

**基于原作者 [Adem Isler 的 CodexControl 初版](https://github.com/ademisler/codexcontrol)改进而来。** 本 Windows 实现与仓库中的 macOS 实现共用项目名称、发布记录和隐私约定。当前版本由维护者独立维护，并保留原作者的 MIT 版权声明。

CodexControl 提供本地账号切换、实时额度查看和 Token 统计。

[项目介绍与下载](https://github.com/ZeusLiu666/codexcontrol#readme) · [隐私说明](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md) · [统一发布流程](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/releasing.md)

### 运行要求

- Windows 10 x64 1809（系统内部版本 17763）或以上，或 Windows 11 x64。
- 安装包和便携包无需用户另装 Python。
- 添加账号、重新登录需要可用的 Codex CLI；额度读取和登录需要网络。
- 可选 SSH 统计需要本机 OpenSSH 客户端、用户自行配置的非交互式认证，以及远端 `python3`。

### 安装与使用

从本仓库 Releases 下载 `CodexControl-<版本>-windows-x64-Setup.exe` 后运行。安装目标为当前用户的 `%LOCALAPPDATA%\Programs\CodexControl`，并创建开始菜单入口。登录后自动启动为可选项，默认不选中。

也可以下载 `CodexControl-<版本>-windows-x64-portable.zip`，解压后直接运行 `CodexControl.exe`。便携包不携带预置账号，仍使用 `%APPDATA%\CodexControl` 保存运行数据。

程序提供系统托盘和账号窗口，可添加、刷新、重新登录、切换、移除账号并打开账号目录。额度接口提供时会分别显示 5 小时与 7 天窗口及重置时间。本地 Token 统计记录首次运行后的新增事件，并展示近 7 天汇总。SSH 统计默认关闭，启用方法见[主说明](https://github.com/ZeusLiu666/codexcontrol#readme)。

切换账号会更新 `~/.codex/auth.json`、同步 Codex 全局状态，并保存和恢复对应账号的 Desktop 会话缓存。切换时可能关闭并重启 Codex Desktop，请提前保存工作。不同版本 Desktop 的缓存布局可能变化，相关兼容逻辑与测试位于本目录源码中。

卸载安装程序会移除程序和快捷方式，保留 `%APPDATA%\CodexControl` 中的账号与运行数据。该目录可能包含有效认证令牌和会话，清理方法见[隐私说明](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md)。

### 从源码运行

建议使用 Python 3.12 x64，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements.txt
.\.venv\Scripts\python.exe .\windows\CodexControlWindows.pyw
```

从源码运行也会使用当前用户的应用数据目录。测试和界面验证请使用临时用户目录及合成账号，避免接触真实登录状态。

### 构建独立 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build.ps1 `
  -Python .\.venv\Scripts\python.exe -InstallDependencies -Clean
```

输出为 `windows\dist\CodexControl.exe`。可以用 `-Python <python.exe路径>` 指定 Python，用 `-Version <版本号>` 指定文件版本。`-InstallDependencies` 安装 `requirements-build.txt` 中固定版本的构建依赖；依赖已安装时可以省略此选项。

### 构建安装包与便携包

需要官方 Inno Setup 6.5.3 编译器，脚本会核对编译器哈希。版本号用实际发布版本替换：

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\package_release.ps1 `
  -Python .\.venv\Scripts\python.exe -Version 1.2.8 -InstallDependencies -Clean
```

如构建脚本无法自动找到编译器，传入 `-InnoSetupCompiler <ISCC.exe路径>`；也支持 `-Python <python.exe路径>`。输出位于 `ReleaseArtifacts`：

- `CodexControl-<版本>-windows-x64-Setup.exe`
- `CodexControl-<版本>-windows-x64-portable.zip`
- `SHA256SUMS-windows.txt`

便携包中的 `install.ps1` 可将程序复制到当前用户程序目录。调用前请阅读参数；下面示例保持登录后自动启动关闭：

```powershell
# 在解压目录中执行；显式关闭脚本的登录后自动启动选项
& .\install.ps1 `
  -SourceExe .\CodexControl.exe -EnableStartup:$false -Launch
```

### 测试

在仓库根目录的隔离环境中执行。测试还会验证发布工具，需要安装构建依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
```

发布前还需验证安装、启动、系统托盘、卸载、便携包启动及压缩包内容，并检查最终 EXE、安装包、压缩包中没有发布者的本机路径或私有数据。不要通过真实账号切换来做自动化冒烟测试。

### 本地数据与隐私

`%APPDATA%\CodexControl` 中可能包含账号信息、认证备份、托管账号目录、额度快照、Token 统计及 Desktop 会话副本。它们不保证额外加密，不应随 bug 报告或源码上传。发布脚本只应打包明确列出的程序与说明文件，不能直接压缩应用数据目录。完整约定见 [PRIVACY.md](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md)。
