# Changelog

[English](#english) | [中文](#中文)

## English

All notable changes to this project will be documented in this file. Earlier version entries describe historical behavior, not necessarily the current release.

The format is based on Keep a Changelog and this project uses Semantic Versioning.

### [1.2.8] - 2026-10-15

#### Cross-platform release

- Unified the macOS and Windows project introduction, download guidance, and privacy documentation.
- Provided complete English and Chinese versions of the project documentation.
- Added prominent credit explaining that this independently maintained derivative is based on and improved from the original [CodexControl by Adem Isler](https://github.com/ademisler/codexcontrol), preserving the upstream MIT notices.
- Added a per-user Windows x64 installer, portable package, and SHA-256 checksums.
- Disabled remote Token collection until the user explicitly configures their own SSH targets.
- Removed private infrastructure descriptions and unverified screenshots from the public source tree.
- Rebuilt macOS installers without build-machine provenance metadata; disabled extended attributes in future macOS archives.

#### Added

- Per-account local Token analytics for today, the last 7 days, and all tracked time
- Optional incremental SSH collection of Token events from user-configured hosts, with provider-account mapping and pending unknown-account records
- Input, cached input, output, and reasoning Token breakdowns sourced from local Codex session events
- A native macOS WidgetKit extension with small, medium, and large desktop widgets
- Widget snapshots with masked account identifiers and no authentication data; masked labels are not a guarantee of anonymity
- A GitHub-style 7-day Token contribution heatmap with per-day hover details
- An unbounded main account list with explicit empty-state support and no artificial account-count limit
- Compact 14-point daily cells and a rolling date range for the 7-day Token view
- A compact inline Less-to-More legend that removes excess vertical space from the weekly heatmap
- Full-width, evenly distributed weekly cells enlarged to 20 points with more readable Token analytics typography
- An adaptive account search bar that appears only when more than five accounts are present
- Rebalanced weekly heatmap spacing so the cells sit visually centered between the legend and Token totals
- Matched the weekly heatmap's lower visual gap to its upper gap by tightening the Token totals spacing

#### Fixed

- Prevent removed accounts from reappearing after managed-home discovery on macOS and Windows
- Recover stale managed account credentials from newer matching auth homes before surfacing refresh-token errors
- Decode Plus account credit balances when the Codex usage API returns `credits.balance` as a string
- Match accounts by the complete auth-subject and provider-account identity so different users in one workspace remain separate
- Resolve the active account only from the exact composite login identity
- Detect exact duplicated credentials, keep one canonical active row, and mark the repair slot for reauthentication
- Remove the account-level Primary label so only the current login is marked Active
- Remove duplicated full-width quota progress bars from expanded account rows
- Build the macOS widget as a real app extension with the standard `NSExtensionMain` entry point so WidgetKit can discover it

### [1.1.3] - 2026-04-23

#### Added

- Windows account switching now syncs `.codex-global-state.json` and `.codex-global-state.json.bak` creator IDs when replacing the active account
- Windows restart flow now backs up and restores Codex Desktop MSIX session state under `%LOCALAPPDATA%\Packages\OpenAI.Codex*`
- Regression coverage for Windows account switching, global state rewrites, and desktop session handoff
- Windows account-switching fix notes under `windows/ACCOUNT_SWITCH_FIX.md`

#### Changed

- Replaced the repository Windows implementation with the validated fixed Windows source from the working build
- Updated release metadata, landing page references, and documentation for `1.1.3`

#### Fixed

- Windows account switching after recent Codex Desktop updates, where copying only `auth.json` could leave Codex Desktop on a stale session or login screen

### [1.1.2] - 2026-04-19

#### Fixed

- Windows packaged account switching so the hidden PowerShell restart helper no longer uses `DETACHED_PROCESS`, which previously prevented Codex Desktop from relaunching after a switch
 
### [1.1.1] - 2026-04-19

#### Added

- Windows-side presentation logic tests covering active account detection and practical quota sorting
- Tracked Windows build assets for the packaged tray application icon and preview image

#### Changed

- Synced the Windows app from the latest stable `CodexControl-dev` implementation
- Updated release metadata and direct download references to `1.1.1`

#### Removed

- Sparkle-based macOS update plumbing, appcast generation, and the in-app update action

#### Fixed

- Windows active-account logic so shared provider IDs do not incorrectly mark multiple accounts as active
- Windows restart command path normalization for a consistent PowerShell launch path
- Windows quota presentation flow with the newer sorting and filtering layer from the stable dev copy

### [1.1.0] - 2026-04-19

#### Added

- Sparkle updater integration for the macOS app with an in-app "Check for Updates" action
- Sparkle bootstrap and appcast generation scripts for local signed release preparation
- Windows release packaging script and GitHub Release asset upload workflow
- Notarization helper script and CI hooks for optional Apple credential-based signing
- Updated website iconography, install cards, and release metadata for the new distribution flow

#### Changed

- Replaced the previous blue Orbit Dial mark with the dark, green, and red production brand
- Updated direct download references from `1.0.0` to `1.1.0`
- Embedded Sparkle.framework into the packaged macOS app bundle

#### Fixed

- macOS packaging so Sparkle's framework and helper bundle are copied into the app
- Website CTA and navigation affordances so external destinations use explicit icons

### [1.0.0] - 2026-04-19

#### Added

- Native macOS menu bar app for Codex quota tracking and account switching
- Windows tray app with quota reads, account management, and switching support
- Static website source and upstream distribution tooling
- GitHub Actions CI and tag-driven release automation
- Release and deployment scripts for macOS packaging and site publishing

#### Changed

- Established CodexControl branding, website assets, and project release structure
- Adopted the Orbit Dial brand mark across the website, app packaging, and release assets
- Professionalized repository surface, documentation, and release readiness

#### Fixed

- Weekly quota window handling for paid and Team accounts
- Active account switching behavior on macOS
- Account removal confirmation flow on macOS
- Window-specific quota coloring and account sorting logic

## 中文

本文件记录项目的所有重要变更。较早版本的条目描述当时的行为，不一定代表当前版本。

格式参考 Keep a Changelog，项目采用语义化版本控制（Semantic Versioning）。

### [1.2.8] - 2026-10-15

#### 跨平台发布

- 统一 macOS 与 Windows 的项目介绍、下载指引和隐私文档。
- 为项目文档提供完整英文和中文版本。
- 显著注明本项目基于原作者 [Adem Isler 的 CodexControl 初版](https://github.com/ademisler/codexcontrol)改进而来，是独立维护的衍生版本，并保留上游 MIT 声明。
- 为 Windows x64 增加按当前用户安装的安装包、便携包及 SHA-256 校验值。
- 在用户主动配置自己的 SSH 目标之前，禁用远程 Token 采集。
- 从公开源码树中移除私人基础设施描述及未经核验的截图。
- 重建 macOS 安装包，去除构建机器来源元数据；后续 macOS 归档不再包含扩展属性。

#### 新增

- 按账号统计本地 Token，覆盖今日、最近 7 天及全部已跟踪时段。
- 可选从用户配置的 SSH 主机增量采集 Token 事件，支持服务商账号映射，并暂存归属未知账号的记录。
- 根据本地 Codex 会话事件，分别统计输入、缓存输入、输出及推理 Token。
- 原生 macOS WidgetKit 扩展，提供小、中、大三种尺寸的桌面小组件。
- 小组件快照使用遮蔽后的账号标识且不包含认证数据；遮蔽标签不保证匿名。
- GitHub 风格的 7 天 Token 贡献热力图，可悬停查看每天的明细。
- 主账号列表取消数量上限，明确支持空状态，不人为限制账号数。
- 7 天 Token 视图使用紧凑的 14 点每日单元格与滚动日期范围。
- 紧凑的行内“少到多”图例，减少每周热力图多余的垂直留白。
- 每周单元格铺满宽度并均匀分布，尺寸增大到 20 点，同时改善 Token 统计文字的可读性。
- 自适应账号搜索栏，仅在账号超过五个时显示。
- 重新平衡每周热力图的间距，使单元格在图例与 Token 合计之间视觉居中。
- 收紧 Token 合计的间距，使每周热力图下方的视觉留白与上方一致。

#### 修复

- 防止 macOS 和 Windows 上已移除的账号在扫描受管理账号目录后重新出现。
- 在提示刷新令牌错误之前，先从身份匹配且较新的认证目录恢复受管理账号中过期的凭据。
- 当 Codex 用量接口以字符串返回 `credits.balance` 时，正确解析 Plus 账号的点数余额。
- 使用完整的认证主体与服务商账号身份匹配账号，使同一工作区的不同用户保持独立。
- 仅依据完全匹配的组合登录身份判断当前账号。
- 检测完全重复的凭据，保留一条规范的当前账号记录，并将待修复记录标记为需要重新认证。
- 移除账号级“Primary”标签，仅将当前登录标记为“Active”。
- 移除展开的账号行中重复的全宽额度进度条。
- 使用标准 `NSExtensionMain` 入口将 macOS 小组件构建为真正的应用扩展，使 WidgetKit 能够发现它。

### [1.1.3] - 2026-04-23

#### 新增

- Windows 切换账号替换当前账号时，同步 `.codex-global-state.json` 和 `.codex-global-state.json.bak` 中的创建者 ID。
- Windows 重启流程备份并恢复 `%LOCALAPPDATA%\Packages\OpenAI.Codex*` 下的 Codex Desktop MSIX 会话状态。
- 增加 Windows 账号切换、全局状态重写与桌面会话交接的回归测试。
- 在 `windows/ACCOUNT_SWITCH_FIX.md` 中增加 Windows 账号切换修复说明。

#### 调整

- 使用工作构建中已经验证修复的 Windows 源码替换仓库内的 Windows 实现。
- 将发布元数据、落地页引用和文档更新到 `1.1.3`。

#### 修复

- 修复近期 Codex Desktop 更新后的 Windows 账号切换问题：仅复制 `auth.json` 可能使 Codex Desktop 停留在旧会话或登录界面。

### [1.1.2] - 2026-04-19

#### 修复

- 修复 Windows 打包版本的账号切换：隐藏的 PowerShell 重启辅助程序不再使用 `DETACHED_PROCESS`，此前该标志会阻止切换后重新启动 Codex Desktop。

### [1.1.1] - 2026-04-19

#### 新增

- Windows 展示逻辑测试，覆盖当前账号识别与按实际可用性进行的额度排序。
- 将 Windows 打包托盘应用的图标和预览图构建资源纳入版本管理。

#### 调整

- 从最新稳定的 `CodexControl-dev` 实现同步 Windows 应用。
- 将发布元数据及直接下载引用更新到 `1.1.1`。

#### 移除

- 移除基于 Sparkle 的 macOS 更新机制、appcast 生成及应用内更新操作。

#### 修复

- 修复 Windows 当前账号识别逻辑，防止共享服务商 ID 导致多个账号被错误标记为当前账号。
- 规范 Windows 重启命令的路径，确保 PowerShell 启动路径一致。
- 使用稳定开发副本中的新版排序与过滤层修复 Windows 额度展示流程。

### [1.1.0] - 2026-04-19

#### 新增

- 在 macOS 应用中集成 Sparkle 更新器，并提供应用内“Check for Updates”（检查更新）操作。
- 增加 Sparkle 引导与 appcast 生成脚本，用于在本地准备已签名的发布版本。
- 增加 Windows 发布打包脚本与 GitHub Release 附件上传工作流。
- 增加公证辅助脚本和 CI 接入点，可选使用 Apple 凭据执行签名。
- 为新的分发流程更新网站图标、安装卡片和发布元数据。

#### 调整

- 将此前蓝色的 Orbit Dial 标志替换为深色、绿色和红色的正式品牌标志。
- 将直接下载引用从 `1.0.0` 更新到 `1.1.0`。
- 在打包的 macOS 应用包中嵌入 Sparkle.framework。

#### 修复

- 修复 macOS 打包，确保 Sparkle 框架及其辅助程序包被复制到应用中。
- 改善网站行动按钮（CTA）和导航的可识别性，为外部目标使用明确的图标。

### [1.0.0] - 2026-04-19

#### 新增

- 原生 macOS 菜单栏应用，用于跟踪 Codex 额度及切换账号。
- Windows 托盘应用，支持读取额度、管理账号和切换账号。
- 静态网站源码及上游分发工具。
- GitHub Actions CI 与按标签触发的自动发布。
- macOS 打包与网站发布的发布及部署脚本。

#### 调整

- 建立 CodexControl 品牌、网站资源和项目发布结构。
- 在网站、应用打包及发布资源中统一采用 Orbit Dial 品牌标志。
- 完善仓库展示、文档及发布准备工作。

#### 修复

- 付费账号与 Team 账号的每周额度窗口处理。
- macOS 上的当前账号切换行为。
- macOS 上的账号移除确认流程。
- 按不同额度窗口着色及账号排序的逻辑。
