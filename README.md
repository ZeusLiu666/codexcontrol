# CodexControl · ZeusLiu 定制版

基于 [Adem Isler 的 CodexControl](https://github.com/ademisler/codexcontrol) 修改，原项目采用 MIT 许可证。定制与维护署名：**ZeusLiu**。这不是原作者的官方发行版。

## 安装

适用于 **Apple Silicon（M1 及后续芯片）和 macOS 14 或更新版本**。

1. 从本仓库的 Releases 下载 `CodexControl-1.2.8-macos-arm64.dmg`。
2. 退出正在运行的 CodexControl，打开磁盘映像。
3. 将 `CodexControl.app` 拖入 `Applications`。
4. 从“应用程序”启动，通过菜单栏图标打开面板。

也可使用同一 Release 中的 `.pkg` 标准安装器。两种方式安装同一个应用，只需选择一种。

当前发行版为 **1.2.8，构建 16**，使用本地临时签名，尚未经过 Apple Developer ID 签名及公证。macOS 可能提示验证限制。本包不会更改系统安全设置。

## 本版功能

- 每日用量方格支持悬停查看完整日期与精确 token 数量；点击固定，关闭按钮或 Escape 收起。
- 展示输入、缓存输入、输出与推理数量，标明包含关系。
- 改善菜单栏卡片、剩余额度、重置时间、状态消息和刷新反馈。
- 保留多账户切换、用量统计和桌面小组件。
- 远程用量采集改为本机显式配置，默认不连接任何服务器。

## 隐私与发布范围

安装包仅包含应用程序、图标和署名/许可证文档。源码归档仅包含 macOS 所需源码、测试和构建脚本。两者均不包含个人账户、邮箱、登录 token、SSH 密钥或配置、服务器地址、用量历史、会话日志、真实账户截图和本机构建目录。

安装后的账户与用量数据来自运行该应用的电脑。为兼容旧版本，应用继续使用 `~/Library/Application Support/CodexControl`；已有本机账户可能会正常显示。这里的数据不在安装包内。

## 可选远程用量

在本机创建 `~/Library/Application Support/CodexControl/remote-hosts.json`：

```json
[
  { "host": "codex-server", "isOptional": false },
  { "host": "optional-server", "isOptional": true }
]
```

这些名称是示例，须对应你自己的 `~/.ssh/config` 别名，并预先配置好非交互式 SSH 身份验证。不要把实际配置、密钥或密码提交到仓库。程序不会保存 SSH 密码。未提供配置时不运行远程采集。

## 从源码构建

从 Release 下载 `CodexControl-1.2.8-source-sanitized.zip` 并解压，进入 `CodexControl` 文件夹。需要 Swift 6.1 或更新版本及可用的 macOS 开发工具：

```sh
swift test
./Scripts/package_app.sh
./Scripts/build_installers.sh
```

`package_app.sh` 会编译应用和 Widget，并将完整 LICENSE、NOTICE 放入应用资源。默认使用本地临时签名；设置 `CODE_SIGN_IDENTITY` 可使用自己的 Developer ID Application 证书。安装包生成在 `ReleaseArtifacts`，源码归档不会包含该目录。

本仓库先保持 Private，不添加协作者。安装包和源码备份存放在私有 Release 中。

## 署名与许可

- 原作者：**Adem Isler** — [ademisler/codexcontrol](https://github.com/ademisler/codexcontrol)
- 修改版作者：**ZeusLiu**
- 许可证：[MIT](LICENSE)
- 详细归属：[NOTICE](NOTICE)
