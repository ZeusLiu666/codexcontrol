"""Windows port of the supplied Swift token ledger and SSH mirror.
Ledger field names and first-run/checkpoint semantics intentionally match macOS.
"""
from __future__ import annotations
import base64
import json
import os
import re
import subprocess
import threading
from datetime import datetime, timedelta
from pathlib import Path
from .file_locations import APP_SUPPORT_DIRECTORY, AMBIENT_CODEX_HOME

FIELDS = ('input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_output_tokens', 'total_tokens')
CAMEL = ('inputTokens', 'cachedInputTokens', 'outputTokens', 'reasoningOutputTokens', 'totalTokens')

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2), encoding='utf-8')
    temp.replace(path)

def compact(value):
    for divisor, suffix in ((10**9, 'B'), (10**6, 'M'), (10**3, 'K')):
        if abs(value) >= divisor:
            scaled = value / divisor
            precision = 0 if abs(scaled) >= 100 else 1 if abs(scaled) >= 10 else 2
            return f'{scaled:.{precision}f}'.rstrip('0').rstrip('.') + suffix if precision else f'{scaled:.0f}' + suffix
    return f'{value:,}'

def zero():
    return dict.fromkeys(CAMEL, 0)

def add(left, right):
    return {key: left.get(key, 0) + right.get(key, 0) for key in CAMEL}

class TokenUsageTracker:
    def __init__(self, ledger_path=None, session_roots=None):
        self.path = Path(ledger_path or APP_SUPPORT_DIRECTORY / 'token-usage.json')
        self.roots = session_roots if session_roots is not None else [AMBIENT_CODEX_HOME / 'sessions', AMBIENT_CODEX_HOME / 'archived_sessions', APP_SUPPORT_DIRECTORY / 'remote-token-usage']
        self.ledger = None
        self.lock = threading.RLock()

    def files(self):
        return sorted(p for root in self.roots if Path(root).exists() for p in Path(root).rglob('rollout-*.jsonl'))

    def start(self, active_id, now=None):
        with self.lock:
            now = now or datetime.now().astimezone()
            if self.ledger is None:
                if self.path.exists():
                    self.ledger = json.loads(self.path.read_text(encoding='utf-8'))
                else:
                    checkpoints = {}
                    for path in self.files():
                        with path.open('rb') as handle:
                            size = handle.seek(0, 2)
                            length = min(8192, size)
                            handle.seek(size-length)
                            last = handle.read().rfind(b'\n')
                            checkpoints[path.name] = size-length+last+1 if last >= 0 else 0
                    self.ledger = dict(version=1, trackingStartedAt=now.isoformat(), activeAccountID=str(active_id) if active_id else None,
                                       dailyByAccount={str(active_id): {}} if active_id else {}, checkpoints=checkpoints, updatedAt=now.isoformat())
                    atomic_json(self.path, self.ledger)
                    return self.snapshots(now)
            return self.scan(active_id, now)

    def scan(self, active_id, now=None):
        with self.lock:
            now = now or datetime.now().astimezone()
            if self.ledger is None:
                return self.start(active_id, now)
            target = self.ledger.get('activeAccountID') or (str(active_id) if active_id else None)
            if target:
                days = self.ledger['dailyByAccount']
                days.setdefault(target, {})
                seen = set()
                for path in self.files():
                    if path.name in seen:
                        continue
                    seen.add(path.name)
                    offset = self.ledger['checkpoints'].get(path.name, 0)
                    try:
                        if offset > path.stat().st_size:
                            offset = 0
                        with path.open('rb') as handle:
                            handle.seek(offset)
                            data = handle.read()
                        last = data.rfind(b'\n')
                        if last < 0:
                            continue
                        complete = data[:last+1]
                        for raw in complete.splitlines():
                            try:
                                event = json.loads(raw)
                                payload = event.get('payload') or {}
                                if event.get('type') != 'event_msg' or payload.get('type') != 'token_count':
                                    continue
                                usage = (payload.get('info') or {}).get('last_token_usage')
                                if not isinstance(usage, dict):
                                    continue
                                day = datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).astimezone().date().isoformat()
                                account = event.get('codexcontrol_account_id') or target
                                from uuid import UUID
                                UUID(account)
                                values = {camel: int(usage.get(field, 0) or 0) for field, camel in zip(FIELDS, CAMEL)}
                                account_days = days.setdefault(str(account), {})
                                account_days[day] = add(account_days.get(day, zero()), values)
                            except (ValueError, TypeError, KeyError):
                                continue
                        self.ledger['checkpoints'][path.name] = offset+len(complete)
                    except OSError:
                        continue
            if active_id:
                self.ledger['dailyByAccount'].setdefault(str(active_id), {})
            self.ledger['activeAccountID'] = str(active_id) if active_id else None
            self.ledger['updatedAt'] = now.isoformat()
            atomic_json(self.path, self.ledger)
            return self.snapshots(now)

    def remove_account(self, account_id):
        with self.lock:
            if self.ledger:
                self.ledger['dailyByAccount'].pop(str(account_id), None)
                if self.ledger.get('activeAccountID') == str(account_id):
                    self.ledger['activeAccountID'] = None
                atomic_json(self.path, self.ledger)

    def snapshots(self, now):
        from uuid import UUID
        dates = [(now.astimezone().date()-timedelta(days=i)).isoformat() for i in reversed(range(7))]
        result = {}
        for account, days in self.ledger['dailyByAccount'].items():
            weekly, total = zero(), zero()
            for value in days.values():
                total = add(total, value)
            for date in dates:
                weekly = add(weekly, days.get(date, zero()))
            result[UUID(account)] = dict(today=days.get(dates[-1], zero()), lastSevenDays=weekly, allTime=total,
                daily=[dict(date=date, usage=days.get(date, zero())) for date in dates],
                trackingStartedAt=self.ledger['trackingStartedAt'], updatedAt=self.ledger['updatedAt'])
        return result

def normalize_ssh_hosts(hosts):
    """Accept SSH destinations only, never command-line options or shell input."""
    result = []
    for host in hosts:
        host = host.strip()
        if (host and not host.startswith('-') and len(host) <= 255
                and re.fullmatch(r'[A-Za-z0-9_.@:\[\]-]+', host)
                and host not in result):
            result.append(host)
    return result


def configured_ssh_hosts(value=None):
    """SSH collection is disabled until the user explicitly configures hosts."""
    if value is None:
        value = os.environ.get('CODEXCONTROL_SSH_HOSTS', '')
    return normalize_ssh_hosts(value.split(','))


class RemoteTokenUsageMirror:
    def __init__(self, state_path=None, cache_directory=None, hosts=None):
        self.path = Path(state_path or APP_SUPPORT_DIRECTORY / 'remote-token-usage-state.json')
        self.cache = Path(cache_directory or APP_SUPPORT_DIRECTORY / 'remote-token-usage')
        self.hosts = configured_ssh_hosts() if hosts is None else normalize_ssh_hosts(hosts)
        self.state = None

    def sync(self, accounts, fallback_id):
        if not self.hosts:
            return []
        self.cache.mkdir(parents=True, exist_ok=True)
        if self.state is None:
            self.state = json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else dict(version=1, hosts={})
        mapping = {a.normalized_provider_account_id: str(a.id) for a in accounts if a.normalized_provider_account_id}
        statuses = []
        for host in self.hosts:
            optional = True
            try:
                state = self.state['hosts'].get(host, {})
                flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
                config = subprocess.run(['ssh', '-G', '-o', 'ClearAllForwardings=yes', host], capture_output=True, text=True, timeout=10, creationflags=flags)
                if config.returncode:
                    raise RuntimeError(config.stderr)
                encoded = base64.b64encode(json.dumps(state).encode()).decode()
                script = REMOTE_SCRIPT.replace('__STATE_BASE64__', encoded)
                result = subprocess.run(['ssh', '-T', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=3',
                    '-o', 'ServerAliveInterval=5', '-o', 'ServerAliveCountMax=1', '-o', 'ClearAllForwardings=yes', host, 'python3', '-'],
                    input=script, capture_output=True, text=True, timeout=90, creationflags=flags)
                if result.returncode:
                    raise RuntimeError(result.stderr)
                records = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
                if not any(r.get('kind') == 'state' and r.get('bootstrapped') for r in records):
                    raise RuntimeError('Invalid collector output')
                provider = next((r.get('account_id') for r in records if r.get('kind') == 'meta'), None)
                events = list(state.get('pendingEvents', [])) + [dict(providerAccountID=provider, timestamp=r['timestamp'], usage={camel: int(r['usage'].get(field,0)) for field,camel in zip(FIELDS,CAMEL)}) for r in records if r.get('kind') == 'event']
                pending, ready = [], []
                for event in events:
                    pid = event.get('providerAccountID')
                    account = mapping.get(pid.strip().lower()) if pid else (str(fallback_id) if fallback_id else None)
                    if account:
                        ready.append(dict(timestamp=event['timestamp'], type='event_msg', codexcontrol_account_id=account,
                            payload=dict(type='token_count', info=dict(last_token_usage={field: event['usage'].get(camel,0) for field,camel in zip(FIELDS,CAMEL)}))))
                    else:
                        pending.append(event)
                name = ''.join(c if c.isalnum() or c in '.-_' else '_' for c in host)
                if ready:
                    with (self.cache / f'rollout-remote-{name}.jsonl').open('a', encoding='utf-8') as handle:
                        for event in ready:
                            handle.write(json.dumps(event)+'\n')
                self.state['hosts'][host] = dict(checkpoints={r['file']: r['offset'] for r in records if r.get('kind')=='checkpoint'}, pendingEvents=pending, bootstrapped=True)
                self.state['updatedAt'] = datetime.now().astimezone().isoformat()
                atomic_json(self.path, self.state)
                detail = ('Connected; attributed to active account' if fallback_id else 'Connected; account identity unavailable') if not provider else ('Connected; account is not in CodexControl' if pending else 'Connected' if ready else 'Connected; no new events')
                statuses.append(dict(host=host, isAvailable=True, detail=detail, isOptional=optional))
            except Exception as error:
                text = str(error).lower()
                detail = 'SSH key required' if 'permission denied' in text or 'password' in text else 'SSH timeout' if 'timeout' in text or 'timed out' in text else 'Network unavailable' if 'no route' in text or 'network is unreachable' in text else 'SSH unavailable'
                statuses.append(dict(host=host, isAvailable=False, detail=detail, isOptional=optional))
        return statuses

REMOTE_SCRIPT = '\nimport base64\nimport json\nimport pathlib\nimport time\nimport datetime\n\nstate = json.loads(base64.b64decode("__STATE_BASE64__").decode("utf-8"))\ncheckpoints = dict(state.get("checkpoints", {}))\nbootstrapped = bool(state.get("bootstrapped", False))\ncutoff = time.time() - (7 * 24 * 60 * 60) if not bootstrapped else None\n\ndef emit(value):\n    print(json.dumps(value, separators=(",", ":"), ensure_ascii=True))\n\naccount_id = None\ntry:\n    auth = json.loads((pathlib.Path.home() / ".codex" / "auth.json").read_text())\n    account_id = (auth.get("tokens") or {}).get("account_id")\nexcept Exception:\n    pass\nemit({"kind": "meta", "account_id": account_id})\n\nroots = [pathlib.Path.home() / ".codex" / "sessions", pathlib.Path.home() / ".codex" / "archived_sessions"]\nseen = set()\nfor root in roots:\n    if not root.is_dir():\n        continue\n    for path in sorted(root.glob("**/rollout-*.jsonl")):\n        name = path.name\n        if name in seen:\n            continue\n        seen.add(name)\n        try:\n            size = path.stat().st_size\n            if not bootstrapped and name not in checkpoints and path.stat().st_mtime < cutoff:\n                checkpoints[name] = size\n                emit({"kind": "checkpoint", "file": name, "offset": size})\n                continue\n            offset = int(checkpoints.get(name, 0))\n            if offset > size:\n                offset = 0\n            with path.open("rb") as handle:\n                handle.seek(offset)\n                data = handle.read()\n            final_newline = data.rfind(b"\\n")\n            if final_newline < 0:\n                checkpoints[name] = offset\n                emit({"kind": "checkpoint", "file": name, "offset": offset})\n                continue\n            complete = data[:final_newline + 1]\n            for raw in complete.splitlines():\n                try:\n                    event = json.loads(raw)\n                    if event.get("type") != "event_msg":\n                        continue\n                    payload = event.get("payload") or {}\n                    if payload.get("type") != "token_count":\n                        continue\n                    timestamp = event.get("timestamp")\n                    info = payload.get("info") or {}\n                    usage = info.get("last_token_usage") or {}\n                    if not timestamp or not isinstance(usage, dict):\n                        continue\n                    if cutoff is not None:\n                        try:\n                            parsed = datetime.datetime.fromisoformat(timestamp.replace("Z", "+00:00")).timestamp()\n                            if parsed < cutoff:\n                                continue\n                        except Exception:\n                            continue\n                    values = {key: int(usage.get(key, 0) or 0) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens", "total_tokens")}\n                    emit({"kind": "event", "timestamp": timestamp, "usage": values})\n                except Exception:\n                    continue\n            new_offset = offset + len(complete)\n            checkpoints[name] = new_offset\n            emit({"kind": "checkpoint", "file": name, "offset": new_offset})\n        except (OSError, ValueError):\n            continue\nemit({"kind": "state", "bootstrapped": True})\n'
