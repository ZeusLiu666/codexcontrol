import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch
from types import SimpleNamespace
from codexcontrol_windows.token_usage import TokenUsageTracker, RemoteTokenUsageMirror, REMOTE_SCRIPT, compact
from codexcontrol_windows.models import StoredAccount, StoredAccountSource
from codexcontrol_windows.presentation_logic import AccountIdentityPresentation, is_active_account
from codexcontrol_windows.codex_api import AuthBackedIdentity, _identity_matches_account

def account(subject='user1', provider='workspace', email='person@example.com'):
    now=datetime.now(timezone.utc)
    return StoredAccount(uuid4(),None,email,subject,provider,'C:/accounts/'+subject,StoredAccountSource.MANAGED_BY_APP,now,now)

def event(now,total=220,account_id=None):
    value=dict(timestamp=now.isoformat(),type='event_msg',payload=dict(type='token_count',info=dict(last_token_usage=dict(input_tokens=total-40,cached_input_tokens=80,output_tokens=40,reasoning_output_tokens=10,total_tokens=total))))
    if account_id: value['codexcontrol_account_id']=str(account_id)
    return json.dumps(value)

class PortTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.sessions=self.root/'sessions'; self.sessions.mkdir()
        self.archive=self.root/'archived'; self.archive.mkdir()
        self.log=self.sessions/'rollout-test.jsonl'; self.log.write_text('')
        self.ledger=self.root/'ledger.json'
        self.tracker=TokenUsageTracker(self.ledger,[self.sessions,self.archive])
        self.now=datetime.now().astimezone().replace(hour=12)
        self.first=uuid4(); self.second=uuid4()
    def tearDown(self): self.temp.cleanup()
    def append(self,text):
        with self.log.open('a',encoding='utf-8') as f: f.write(text)
    def test_baseline_and_breakdown(self):
        self.append(event(self.now,100)+'\n')
        self.assertEqual(self.tracker.start(self.first,self.now)[self.first]['allTime']['totalTokens'],0)
        self.append(event(self.now)+'\n')
        snapshot=self.tracker.scan(self.first,self.now)[self.first]
        self.assertEqual(snapshot['today'],dict(inputTokens=180,cachedInputTokens=80,outputTokens=40,reasoningOutputTokens=10,totalTokens=220))
        self.assertEqual(len(snapshot['daily']),7)
        self.assertEqual(self.tracker.scan(self.first,self.now)[self.first]['allTime']['totalTokens'],220)
    def test_transition_settles_previous_account(self):
        self.tracker.start(self.first,self.now); self.append(event(self.now,120)+'\n')
        data=self.tracker.scan(self.second,self.now)
        self.assertEqual(data[self.first]['allTime']['totalTokens'],120)
        self.assertEqual(data[self.second]['allTime']['totalTokens'],0)
        self.append(event(self.now,75)+'\n')
        self.assertEqual(self.tracker.scan(self.second,self.now)[self.second]['today']['totalTokens'],75)
    def test_partial_line_archive_and_reload(self):
        self.tracker.start(self.first,self.now); self.append(event(self.now,90))
        self.assertEqual(self.tracker.scan(self.first,self.now)[self.first]['allTime']['totalTokens'],0)
        self.append('\n'); self.tracker.scan(self.first,self.now)
        self.log.rename(self.archive/self.log.name)
        loaded=TokenUsageTracker(self.ledger,[self.sessions,self.archive]).start(self.first,self.now)
        self.assertEqual(loaded[self.first]['allTime']['totalTokens'],90)
    def test_remote_explicit_account_and_rolling_window(self):
        self.tracker.start(self.first,self.now)
        self.append(event(self.now-timedelta(days=7),90,self.second)+'\n'+event(self.now,120,self.second)+'\n')
        data=self.tracker.scan(self.first,self.now)[self.second]
        self.assertEqual(data['allTime']['totalTokens'],210)
        self.assertEqual(data['lastSevenDays']['totalTokens'],120)
        self.tracker.remove_account(self.second)
        self.assertNotIn(self.second,self.tracker.scan(self.first,self.now))
    def test_composite_identity_and_duplicate_slots(self):
        a,b=account(),account('user2')
        self.assertFalse(a.matches(b))
        identity=AuthBackedIdentity(a.email_hint,a.auth_subject,'team',a.provider_account_id)
        self.assertTrue(is_active_account(a,identity)); self.assertFalse(is_active_account(b,identity))
        self.assertFalse(_identity_matches_account(identity,b.codex_home_path,b))
        duplicate=account(); duplicate.codex_home_path='C:/other'
        presentation=AccountIdentityPresentation([a,b,duplicate])
        self.assertEqual(len(presentation.duplicate_ids),1)
        self.assertNotIn(presentation.active_id(identity),presentation.duplicate_ids)
    def test_remote_pending_mapping_and_no_duplicate_counts(self):
        a=account(); mirror=RemoteTokenUsageMirror(self.root/'remote.json',self.root/'cache',hosts=['build-server'])
        output='\n'.join(json.dumps(x) for x in [dict(kind='meta',account_id=a.provider_account_id),dict(kind='event',timestamp=self.now.isoformat(),usage=dict(total_tokens=120)),dict(kind='checkpoint',file='rollout-r.jsonl',offset=100),dict(kind='state',bootstrapped=True)])
        responses=[SimpleNamespace(returncode=0,stdout='user test\nhostname example\nport 22',stderr=''),SimpleNamespace(returncode=0,stdout=output,stderr='')]
        with patch('codexcontrol_windows.token_usage.subprocess.run',side_effect=responses):
            self.assertTrue(mirror.sync([],None)[0]['isAvailable'])
        self.assertEqual(len(mirror.state['hosts']['build-server']['pendingEvents']),1)
        no_events='\n'.join(json.dumps(x) for x in [dict(kind='meta',account_id=a.provider_account_id),dict(kind='checkpoint',file='rollout-r.jsonl',offset=100),dict(kind='state',bootstrapped=True)])
        with patch('codexcontrol_windows.token_usage.subprocess.run',side_effect=[responses[0],SimpleNamespace(returncode=0,stdout=no_events,stderr='')]):
            mirror.sync([a],None)
        lines=(mirror.cache/'rollout-remote-build-server.jsonl').read_text().splitlines()
        self.assertEqual(len(lines),1); self.assertEqual(json.loads(lines[0])['codexcontrol_account_id'],str(a.id))
    def test_collector_uses_only_token_records(self):
        import io
        from contextlib import redirect_stdout
        home=self.root/'remote-home'; sessions=home/'.codex'/'sessions'; sessions.mkdir(parents=True)
        (home/'.codex'/'auth.json').write_text(json.dumps(dict(tokens=dict(account_id='workspace'))))
        (sessions/'rollout-remote.jsonl').write_text(event(self.now)+'\n'+json.dumps(dict(type='message',content='private conversation'))+'\n')
        stream=io.StringIO()
        with patch('pathlib.Path.home',return_value=home),redirect_stdout(stream):
            exec(REMOTE_SCRIPT.replace('__STATE_BASE64__','e30='),{})
        records=[json.loads(x) for x in stream.getvalue().splitlines()]
        self.assertEqual(len([r for r in records if r['kind']=='event']),1)
        self.assertNotIn('private conversation',stream.getvalue())
    def test_compact_counts(self):
        self.assertEqual(compact(100_000),'100K'); self.assertEqual(compact(12_345),'12.3K')

if __name__=='__main__': unittest.main()
