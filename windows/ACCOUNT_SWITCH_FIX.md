# Account Switch Fix Notes

[English](#english) | [中文](#中文)

## English

### Summary

The Windows app originally switched accounts by copying only `~/.codex/auth.json`.
That was not sufficient for current Codex Desktop builds.

### Root Cause

Two separate state layers were involved:

1. CLI identity state in `~/.codex`
   - `auth.json`
   - `.codex-global-state.json`
   - `.codex-global-state.json.bak`

2. Desktop browser/session state in the Codex MSIX package cache
   - `%LOCALAPPDATA%\\Packages\\OpenAI.Codex_*\\LocalCache\\Roaming\\Codex`

The original switch flow updated only `auth.json`, so Codex Desktop could reopen with:

- a stale `creator_id` in `.codex-global-state.json`, or
- stale browser/session state under the MSIX package cache.

That produced two visible failures:

- switch completed but Codex Desktop still showed the login screen
- in some cases Codex Desktop was terminated but not relaunched because the restart script failed while copying session files

### Fix

#### 1. Sync global CLI state during switch

`windows/codexcontrol_windows/account_manager.py`

- After copying the target `auth.json`, the switch flow now rewrites `creator_id` in:
  - `.codex-global-state.json`
  - `.codex-global-state.json.bak`
- The rewrite is account-aware and replaces the previous provider account id with the target account id.

#### 2. Discover and manage Codex Desktop session state

`windows/codexcontrol_windows/file_locations.py`

- Added discovery of the active Codex MSIX package under:
  - `%LOCALAPPDATA%\\Packages\\OpenAI.Codex*`
- Added resolution of the live desktop session root:
  - `LocalCache\\Roaming\\Codex`
- Defined the session entries that need to be preserved/restored during account switching.

#### 3. Backup and restore desktop session state during restart

`windows/codexcontrol_windows/codex_desktop.py`

- The restart script now:
  - stops Codex Desktop
  - backs up the current desktop session into the managed home of the account being switched away from
  - restores the target account's saved desktop session when available
  - relaunches Codex Desktop

- The script was also hardened:
  - file-path handling for session file copies was fixed
  - backup/restore runs per entry with logging instead of failing the whole restart on the first copy error
  - when the target account has no saved desktop session yet, the script no longer wipes the current live session state

### Important Behavioral Note

If a target account does not yet have a saved `desktop-session` snapshot, the first switch to that account may still require Codex Desktop to reconcile login/session state on its own.
After that account has been active once and its desktop session has been backed up, subsequent switches are expected to behave more consistently.

### Files Changed

- `windows/codexcontrol_windows/account_manager.py`
- `windows/codexcontrol_windows/app.py`
- `windows/codexcontrol_windows/codex_desktop.py`
- `windows/codexcontrol_windows/file_locations.py`
- `windows/tests/test_account_manager.py`
- `windows/tests/test_codex_desktop.py`

## 中文

### 概述

Windows 应用最初仅通过复制 `~/.codex/auth.json` 来切换账号。
对于修复时所针对的 Codex Desktop 构建，这种方式并不足够。

### 根本原因

涉及两层独立状态：

1. `~/.codex` 中的 CLI 身份状态
   - `auth.json`
   - `.codex-global-state.json`
   - `.codex-global-state.json.bak`

2. Codex MSIX 包缓存中的 Desktop 浏览器／会话状态
   - `%LOCALAPPDATA%\\Packages\\OpenAI.Codex_*\\LocalCache\\Roaming\\Codex`

原先的切换流程仅更新 `auth.json`，因此 Codex Desktop 重新打开时可能仍使用：

- `.codex-global-state.json` 中过期的 `creator_id`，或者
- MSIX 包缓存中残留的旧浏览器／会话状态。

这会导致两个可见问题：

- 切换完成后，Codex Desktop 仍显示登录界面；
- 某些情况下，重启脚本在复制会话文件时失败，导致 Codex Desktop 被终止后没有重新启动。

### 修复方式

#### 1. 切换时同步全局 CLI 状态

`windows/codexcontrol_windows/account_manager.py`

- 复制目标 `auth.json` 后，切换流程会重写以下文件中的 `creator_id`：
  - `.codex-global-state.json`
  - `.codex-global-state.json.bak`
- 重写时识别账号，将原服务商账号 ID 替换为目标账号 ID。

#### 2. 发现和管理 Codex Desktop 会话状态

`windows/codexcontrol_windows/file_locations.py`

- 增加在以下路径中查找当前 Codex MSIX 包的逻辑：
  - `%LOCALAPPDATA%\\Packages\\OpenAI.Codex*`
- 增加对正在使用的桌面会话根目录的解析：
  - `LocalCache\\Roaming\\Codex`
- 定义切换账号时需要保留和恢复的会话条目。

#### 3. 重启期间备份和恢复桌面会话状态

`windows/codexcontrol_windows/codex_desktop.py`

- 重启脚本现在会：
  - 停止 Codex Desktop；
  - 将当前桌面会话备份到即将切离账号的受管理目录；
  - 如果目标账号已有保存的桌面会话，则恢复该会话；
  - 重新启动 Codex Desktop。

- 同时增强了脚本的容错能力：
  - 修正复制会话文件时的文件路径处理；
  - 按条目执行并记录备份和恢复，首个复制错误不会导致整个重启失败；
  - 当目标账号尚无已保存的桌面会话时，不再清除当前正在使用的会话状态。

### 重要行为说明

如果目标账号尚无已保存的 `desktop-session` 快照，首次切换到该账号时，可能仍需 Codex Desktop 自行协调登录与会话状态。
该账号至少成功激活一次、并且其桌面会话完成备份后，后续切换预计会更稳定。

### 修改的文件

- `windows/codexcontrol_windows/account_manager.py`
- `windows/codexcontrol_windows/app.py`
- `windows/codexcontrol_windows/codex_desktop.py`
- `windows/codexcontrol_windows/file_locations.py`
- `windows/tests/test_account_manager.py`
- `windows/tests/test_codex_desktop.py`
