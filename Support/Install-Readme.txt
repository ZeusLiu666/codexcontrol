CodexControl 1.4.1 (build 23)
Maintained by CodexControl contributors

INSTALL

Requires Apple Silicon (M1 or newer) and macOS 14 or later.

Quit CodexControl, then drag CodexControl.app to Applications.
Launch it from Applications and click its menu-bar icon.

The .pkg installer from the same Release installs the same app.
Choose either the .dmg or .pkg download.

The app is ad-hoc signed and has not been notarized by Apple.
macOS may show a verification warning.

ABOUT THIS BUILD

This macOS build is part of the unified CodexControl project for macOS and Windows.
It retains account switching, quota tracking, Token analytics, and widgets.

LOCAL DATA

No personal accounts, authentication tokens, SSH configuration, usage history,
or session logs are included. The app uses data on the current computer,
including existing accounts in ~/Library/Application Support/CodexControl.

Remote usage collection is off by default. To enable it, configure your own
~/Library/Application Support/CodexControl/remote-hosts.json locally.
See the repository README for the format and SSH setup.

SOURCE

The complete macOS and Windows source is public in the same repository:
https://github.com/ZeusLiu666/codexcontrol

git clone https://github.com/ZeusLiu666/codexcontrol.git

The GitHub Release includes source archives for the tagged commit.
To build this version from a clone, check out v1.4.1-zeusliu.1.

CREDITS

This independent derivative is based on and improved from the initial version
of CodexControl by Adem Isler.

Original author: Adem Isler
https://github.com/ademisler/codexcontrol
Copyright (c) 2026 Adem Isler

Additional changes by CodexControl contributors; see LICENSE.txt.

MIT License; see LICENSE.txt and NOTICE.txt.

---

CodexControl 1.4.1（构建 23）
由 CodexControl contributors 维护

安装

需要 Apple Silicon（M1 或更新芯片）及 macOS 14 或更新版本。

先退出 CodexControl，再把 CodexControl.app 拖到 Applications；
从“应用程序”启动后，点击菜单栏图标打开面板。

同一 Release 中的 .pkg 安装器安装的是同一个应用，选择一种方式即可。

应用使用本地临时签名（ad-hoc），尚未经过 Apple 公证，
macOS 可能显示验证提示。

本次构建

本 macOS 构建属于 macOS 与 Windows 共用的 CodexControl 项目。
保留账号切换、额度查询、Token 统计与桌面小组件。

本机数据

不包含个人账户、登录凭据、SSH 配置、用量记录或会话日志。
应用读取当前电脑上的数据，包括
~/Library/Application Support/CodexControl 中已有的账户。

远程采集默认关闭。如需启用，请在本机配置自己的
~/Library/Application Support/CodexControl/remote-hosts.json。
文件格式与 SSH 配置要求见仓库 README。

源码

完整的 macOS 与 Windows 源码在同一个公开仓库中：
https://github.com/ZeusLiu666/codexcontrol

git clone https://github.com/ZeusLiu666/codexcontrol.git

GitHub Release 提供该版本标签对应的源码归档。
从克隆的仓库构建此版本时，请检出 v1.4.1-zeusliu.1。

署名

本独立衍生版本基于原作者 Adem Isler 的 CodexControl 初版改进而来。

原作者：Adem Isler
https://github.com/ademisler/codexcontrol
Copyright (c) 2026 Adem Isler

其他修改由 CodexControl contributors 维护；完整归属见 LICENSE.txt。

遵循 MIT 许可证；详见 LICENSE.txt 和 NOTICE.txt。
