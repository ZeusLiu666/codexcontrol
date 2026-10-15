# Privacy and release data boundaries · 隐私与发布数据边界

[English](#english) · [中文](#中文)

## English

CodexControl manages Codex accounts locally. Both macOS and Windows need access to sensitive sign-in data to query quota and switch accounts. Public source and installers must not include the publisher's or testers' personal data.

### What the app accesses

| Data | Purpose and destination |
| --- | --- |
| Codex `auth.json`, access tokens, and refresh tokens | Read identity and authenticate requests to OpenAI; refreshed credentials may be written back locally |
| Email, display name, account ID, plan, and quota snapshots | Maintain the local account list and display account status |
| Local Codex session events | Parse Token usage and read checkpoints locally; complete conversations are not uploaded to a project server |
| Windows Codex Desktop state, session caches, and auth backups | Save, restore, and synchronize account sessions locally during switching; these may contain active sign-in sessions |
| Optional SSH configuration and remote statistics | Used only after the user explicitly configures remote targets, as described below |
| macOS Widget snapshots | Provide masked account labels, Token totals, and quota values to a local widget; masking is not anonymity or encryption |

Quota and sign-in features communicate with OpenAI. Enabling SSH collection also connects to the servers configured by the user. Local-first does not mean fully offline; each network service's own data practices still apply.

### Storage and protection

- macOS app data: `~/Library/Application Support/CodexControl`.
- Windows app data: `%APPDATA%\CodexControl`.
- Current Codex sign-in and sessions: the user's `~/.codex` directory.
- Windows Desktop caches: the current user's Codex app-data or MSIX package directories; some state is copied into CodexControl-managed account directories when switching.
- macOS Widget: snapshot files in the app-data directory and the local Widget container.

App data may include `accounts.json`, `snapshots.json`, `token-usage.json`, managed account homes, authentication backups, remote statistics, and Desktop session copies. The app may also migrate data from older app-data directories.

**These files are not guaranteed additional encryption.** JSON, authentication files, and session backups may be readable by other software with access to the same system account. Operating-system permissions, disk encryption, and local security settings remain the user's responsibility. Do not publish app data, `~/.codex`, SSH directories, or session caches in repositories, public sync folders, or support attachments that have not been redacted.

### Optional SSH statistics

Remote connections are disabled by default on both systems. Windows uses the `CODEXCONTROL_SSH_HOSTS` environment variable; macOS uses `remote-hosts.json`. See the [main README](../README.md#optional-remote-statistics) for formats. Hostnames, usernames, ports, and private keys are user configuration and must not be embedded in public source or release documentation. The app uses non-interactive SSH authentication and does not request or save SSH passwords.

The collector reads the account identifier from remote Codex authentication data and Token events from remote session logs. It returns account identifiers, timestamps, numeric usage, and file checkpoints. It does not copy complete remote authentication files or conversation text into the local statistics cache. That cache still contains sensitive account, time, and host associations and must not be treated as anonymous public data.

The first remote collection reads relevant events from the last seven days; later collections use incremental checkpoints. Disabling the targets and restarting the app stops new remote connections, but does not automatically remove existing local caches.

### Removing your data

After quitting CodexControl, you can remove its app-data directory for the relevant system to clear the account list, authentication copies, Token ledger, statistics caches, and session backups stored there. macOS Widget snapshots may also need to be removed separately from the widget container. The Windows uninstaller preserves app data by default. Removing one account does not securely erase a disk or revoke every token that has been issued.

Codex manages `~/.codex` and its own Desktop data. Removing CodexControl's app-data directory does not remove those directories. Use Codex or OpenAI account/session controls to sign out or revoke credentials. Before deleting anything, check which accounts and files you still need so that you do not remove another tool's data.

### Public release requirements

Public source, installers, and attachments must meet these boundaries:

- Include program source or build results, public dependencies, synthetic test data, documentation, and required licenses.
- Exclude real accounts, tokens, private SSH targets, personal paths, session logs, runtime screenshots, browser caches, app-data directories, and deployment credentials.
- Do not copy developer Git identity settings, unnecessary personal metadata from history, credential-bearing remotes, or personal build-directory information.
- Publish UI screenshots only when all displayed data is demonstrably synthetic; remove or recreate images whose origin cannot be verified.
- Preserve the original and third-party copyright attribution required by open-source licenses. Review legal attribution separately from the current publisher's private account data.

`.gitignore` helps prevent accidental additions; it is not a leak detector. Tracked files, commit history, archive contents, and compiled path strings require separate checks. See [releasing.md](./releasing.md) for release checks.

---

## 中文

CodexControl 在本机管理 Codex 账号。macOS 和 Windows 版本都需要访问敏感登录数据才能查询额度和切换账号。公开源码与安装包应为空账号状态，不得携带发布者或测试者的个人数据。

### 程序会访问什么

| 数据 | 用途与去向 |
| --- | --- |
| Codex `auth.json`、访问令牌与刷新令牌 | 读取身份、向 OpenAI 认证和额度接口发送请求；刷新后可能更新本地认证文件 |
| 邮箱、显示名称、账号 ID、套餐与额度快照 | 在本地保存账号清单并展示状态 |
| 本地 Codex 会话事件 | 在本机解析 Token 使用量和读取进度，不作为完整对话上传至项目服务器 |
| Windows Codex Desktop 状态、会话缓存和认证备份 | 切换账号时在本地保存、恢复和同步，可能含有效登录会话 |
| 可选 SSH 配置与远端统计 | 仅在主动配置远程目标后使用，详见下文 |
| macOS Widget 快照 | 向本地桌面组件提供遮盖后的账号标签、Token 汇总和额度值；遮盖不是匿名化或加密 |

额度和登录功能需要与 OpenAI 服务通信。开启 SSH 统计后还会连接用户配置的服务器。本地优先不代表完全离线，网络服务各自的数据处理规则仍适用。

### 存储位置与保护范围

- macOS 应用数据：`~/Library/Application Support/CodexControl`。
- Windows 应用数据：`%APPDATA%\CodexControl`。
- 当前 Codex 登录和会话：用户的 `~/.codex` 目录。
- Windows Desktop 缓存：对应用户的 Codex 应用数据或 MSIX 包数据目录；切换时部分状态会复制到 CodexControl 管理的账号目录。
- macOS Widget：应用数据目录以及本机 Widget 容器中的快照文件。

应用目录可能包含 `accounts.json`、`snapshots.json`、`token-usage.json`、托管账号目录、认证备份、远程统计与 Desktop 会话副本。程序也可能迁移旧版应用数据目录。

**这些文件不保证使用额外加密。** JSON、认证文件和会话备份可能被能读取该系统账号文件的其他程序访问。操作系统文件权限、磁盘加密与本机安全配置由使用者管理。不要将应用数据、`~/.codex`、SSH 目录或会话缓存纳入公开仓库、公开同步目录或未经脱敏的支持附件。

### 可选 SSH 统计

两个系统均默认关闭远程连接。Windows 通过 `CODEXCONTROL_SSH_HOSTS` 环境变量主动配置；macOS 通过 `remote-hosts.json` 主动配置。具体格式见[主说明](../README.md#可选远程统计)。目标主机、用户名、端口和私钥由使用者自行配置，不应写进公开源码或发布文档。程序使用非交互式 SSH 认证，不要求输入或保存 SSH 密码。

采集器在远端读取 Codex 认证中的账号标识，以及会话日志中的 Token 统计事件；返回账号标识、时间戳、数值统计及文件读取检查点。它不会将完整远端认证文件或对话正文复制到本地统计缓存。远程统计缓存仍包含账号标识、时间和主机关联等敏感元数据，不能当作匿名数据公开。

首次远程采集读取最近 7 天范围内的事件，后续使用检查点增量读取。停用远程目标并重新启动程序后，新的远程连接停止；此前的本地缓存不自动删除。

### 清理自己的数据

退出 CodexControl 后，可以删除对应系统的 CodexControl 应用数据目录，以清除其中的账号清单、认证副本、Token 账本、统计缓存和会话备份。macOS Widget 快照也可能需要从组件容器中单独删除。卸载 Windows 安装程序默认保留应用数据目录，移除单个账号也不等于擦除磁盘或撤销所有已发出的令牌。

`~/.codex` 和 Codex Desktop 自己的用户数据由 Codex 管理，删除 CodexControl 的应用目录不会将它们一并清除。若要退出 Codex 登录或撤销凭据，请使用 Codex / OpenAI 提供的相应账号与会话管理功能。删除前自行确认仍需要的账号与数据，避免误删其他工具的文件。

### 公开发行的要求

发布源码、安装包和附件必须遵守以下边界：

- 包含程序源码或构建结果、公开依赖、合成测试数据、说明和必要许可证。
- 不包含真实账号、认证令牌、私人 SSH 目标、个人文件路径、会话日志、运行截图、浏览器缓存、应用数据目录或部署凭据。
- 不复制开发者的 Git 身份设置、历史中不必要的个人元数据、认证过的远程地址或构建时的个人目录信息。
- 仅在能确认完全使用合成数据时发布界面截图；无法确认的图片应移除或重新生成。
- 保留开源许可证要求的原作者与第三方版权归属。版权署名与当前发布者的私人账号数据应分别审查。

`.gitignore` 用于减少误提交，不是泄露检测工具。已经跟踪的文件、提交历史、归档内部和编译后的路径字符串需要单独检查。详细构建与发布核对见 [releasing.md](./releasing.md)。
