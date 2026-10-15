# CodexControl for Windows

CodexControl 的 Windows 实现，与仓库中的 macOS 实现共用项目名称、发布记录和隐私约定。

Windows implementation of CodexControl: local account switching, live quota tracking, and Token statistics.

[项目介绍与下载](https://github.com/ZeusLiu666/codexcontrol#下载与安装) · [隐私说明](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md) · [统一发布流程](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/releasing.md)

## 运行要求

- Windows 10 x64 1809（系统内部版本 17763）或以上，或 Windows 11 x64。
- 安装包和便携包无需用户另装 Python。
- 添加账号、重新登录需要可用的 Codex CLI；额度读取和登录需要网络。
- 可选 SSH 统计需要本机 OpenSSH 客户端、用户自行配置的非交互式认证，以及远端 `python3`。

## 安装与使用

从本仓库 Releases 下载 `CodexControl-<版本>-windows-x64-Setup.exe` 后运行。安装目标为当前用户的 `%LOCALAPPDATA%\Programs\CodexControl`，并创建开始菜单入口。登录后自动启动为可选项，默认不选中。

也可以下载 `CodexControl-<版本>-windows-x64-portable.zip`，解压后直接运行 `CodexControl.exe`。便携包不携带预置账号，仍使用 `%APPDATA%\CodexControl` 保存运行数据。

程序提供系统托盘和账号窗口，可添加、刷新、重新登录、切换、移除账号并打开账号目录。额度接口提供时会分别显示 5 小时与 7 天窗口及重置时间。本地 Token 统计记录首次运行后的新增事件，并展示近 7 天汇总。SSH 统计默认关闭，启用方法见[主说明](https://github.com/ZeusLiu666/codexcontrol#可选远程统计)。

切换账号会更新 `~/.codex/auth.json`、同步 Codex 全局状态，并保存和恢复对应账号的 Desktop 会话缓存。切换时可能关闭并重启 Codex Desktop，请提前保存工作。不同版本 Desktop 的缓存布局可能变化，相关兼容逻辑与测试位于本目录源码中。

卸载安装程序会移除程序和快捷方式，保留 `%APPDATA%\CodexControl` 中的账号与运行数据。该目录可能包含有效认证令牌和会话，清理方法见[隐私说明](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md#清理自己的数据)。

## 从源码运行

建议使用 Python 3.12 x64，在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements.txt
.\.venv\Scripts\python.exe .\windows\CodexControlWindows.pyw
```

从源码运行也会使用当前用户的应用数据目录。测试和界面验证请使用临时用户目录及合成账号，避免接触真实登录状态。

## 构建独立 EXE

```powershell
powershell -ExecutionPolicy Bypass -File .\windows\build.ps1 `
  -Python .\.venv\Scripts\python.exe -InstallDependencies -Clean
```

输出为 `windows\dist\CodexControl.exe`。可以用 `-Python <python.exe路径>` 指定 Python，用 `-Version <版本号>` 指定文件版本。`-InstallDependencies` 安装 `requirements-build.txt` 中固定版本的构建依赖；依赖已安装时可以省略此选项。

## 构建安装包与便携包

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

## 测试

在仓库根目录的隔离环境中执行。测试还会验证发布工具，需要安装构建依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\windows\requirements-build.txt
$env:PYTHONPATH = (Resolve-Path .\windows).Path
.\.venv\Scripts\python.exe -m unittest discover -s .\windows\tests -v
```

发布前还需验证安装、启动、系统托盘、卸载、便携包启动及压缩包内容，并检查最终 EXE、安装包、压缩包中没有发布者的本机路径或私有数据。不要通过真实账号切换来做自动化冒烟测试。

## 本地数据与隐私

`%APPDATA%\CodexControl` 中可能包含账号信息、认证备份、托管账号目录、额度快照、Token 统计及 Desktop 会话副本。它们不保证额外加密，不应随 bug 报告或源码上传。发布脚本只应打包明确列出的程序与说明文件，不能直接压缩应用数据目录。完整约定见 [PRIVACY.md](https://github.com/ZeusLiu666/codexcontrol/blob/main/docs/PRIVACY.md)。
