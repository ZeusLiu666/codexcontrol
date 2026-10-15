from __future__ import annotations
import json
import os
import struct
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from codexcontrol_windows import codex_desktop as desktop
from codexcontrol_windows import file_locations
from codexcontrol_windows.app import CodexControlWindowsApp

@unittest.skipUnless(os.name == 'nt', 'Windows native restart integration')
class NativeRestartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.status=self.root/'status.json'
        self.log=self.root/'restart.log'
    def tearDown(self): self.temp.cleanup()
    def run_script(self,script):
        path=self.root/'test.ps1'; path.write_text(script,encoding='utf-8-sig')
        return subprocess.run(desktop.build_restart_command(path),capture_output=True,text=True,encoding='utf-8',errors='replace',creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
    def pe(self,path,subsystem,magic=0x20b):
        path.parent.mkdir(parents=True,exist_ok=True)
        data=bytearray(256); struct.pack_into('<H',data,0,0x5a4d); struct.pack_into('<I',data,0x3c,64)
        struct.pack_into('<I',data,64,0x4550); struct.pack_into('<H',data,88,magic); struct.pack_into('<H',data,156,subsystem)
        path.write_bytes(data)
    def test_executable_selection_rejects_cli_and_other_chatgpt(self):
        gui=self.root/'OpenAI.Codex_test'/'app'/'ChatGPT.exe'; self.pe(gui,2)
        cli=self.root/'OpenAI'/'Codex'/'bin'/'test'/'codex.exe'; self.pe(cli,3)
        other=self.root/'standalone'/'ChatGPT.exe'; self.pe(other,2)
        pe32=self.root/'legacy'/'Codex.exe'; self.pe(pe32,2,0x10b)
        corrupt=self.root/'bad.exe'; corrupt.write_bytes(b'MZ')
        functions=desktop.RESTART_FLOW.split('\ntry {',1)[0]
        script=functions+'\n@('+','.join('(Test-DesktopPath '+desktop._powershell_literal_path(p)+')' for p in (gui,cli,other,pe32,corrupt))+') | ConvertTo-Json -Compress'
        result=self.run_script(script)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout),[True,False,False,True,False])
    def test_complete_hidden_restart_with_isolated_gui_process(self):
        csc=Path(os.environ['WINDIR'])/'Microsoft.NET'/'Framework64'/'v4.0.30319'/'csc.exe'
        if not csc.exists(): self.skipTest('Fixture compiler unavailable')
        exe=self.root/'OpenAI.Codex_fixture'/'app'/'ChatGPT.exe'; exe.parent.mkdir(parents=True)
        source=self.root/'fixture.cs'
        source.write_text('using System; using System.IO; using System.Diagnostics; using System.Threading; class Fixture { static void Main() { File.AppendAllText(Environment.GetCommandLineArgs()[0] + ".starts", Process.GetCurrentProcess().Id.ToString() + "\\n"); Thread.Sleep(60000); } }',encoding='utf-8')
        compile_result=subprocess.run([str(csc),'/nologo','/target:winexe','/out:'+str(exe),str(source)],capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
        self.assertEqual(compile_result.returncode,0,compile_result.stdout)
        first=subprocess.Popen([str(exe)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
        session=self.root/'session'; session.mkdir(); (session/'Local State').write_text('previous')
        restore=self.root/'restore'; restore.mkdir(); (restore/'Local State').write_text('target')
        backup=self.root/'backup'
        target_auth=self.root/'target-auth.json'; target_auth.write_text('{"test":"target"}')
        ambient_auth=self.root/'ambient-auth.json'; ambient_auth.write_text('{"test":"old"}')
        helper=None; second_pid=None
        try:
            marker=Path(str(exe)+'.starts')
            deadline=time.monotonic()+5
            while not marker.exists() and time.monotonic()<deadline: time.sleep(.05)
            with patch.object(desktop,'RESTART_STATUS_PATH',self.status),patch.object(desktop,'RESTART_LOG_PATH',self.log):
                script=desktop.build_restart_script(0,session_root=session,backup_destination=backup,restore_source=restore,target_auth_path=target_auth,ambient_auth_path=ambient_auth)
            # Scope discovery to our substitute. It is impossible for this test
            # to select or stop the user's real desktop or backend processes.
            script=script.replace('$allProcesses = @(Get-CimInstance Win32_Process)', '$allProcesses = @(Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -ieq '+desktop._powershell_literal_path(exe)+' })')
            path=self.root/'restart.ps1'; path.write_text(script,encoding='utf-8-sig')
            helper=desktop._launch_hidden_powershell(path)
            self.assertEqual(helper.wait(timeout=20),0,self.log.read_text(encoding='utf-8-sig') if self.log.exists() else '')
            status=json.loads(self.status.read_text(encoding='utf-8-sig'))
            self.assertEqual(status['state'],'complete')
            self.assertIsNotNone(first.poll())
            starts=marker.read_text().splitlines(); self.assertEqual(len(starts),2)
            second_pid=int(starts[1]); self.assertNotEqual(first.pid,second_pid)
            self.assertEqual((backup/'Local State').read_text(),'previous')
            self.assertEqual((session/'Local State').read_text(),'target')
            self.assertEqual(ambient_auth.read_text(),target_auth.read_text())
            log=self.log.read_text(encoding='utf-8-sig')
            self.assertLess(log.index('All Codex Desktop GUI processes exited'),log.index('Restored desktop session state'))
            self.assertLess(log.index('Restored desktop session state'),log.index('Codex Desktop GUI relaunched'))
        finally:
            if helper and helper.poll() is None: helper.kill(); helper.wait()
            if first.poll() is None: first.kill(); first.wait()
            if second_pid:
                subprocess.run(['taskkill.exe','/PID',str(second_pid),'/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
            else:
                marker=Path(str(exe)+'.starts')
                if marker.exists():
                    for pid in marker.read_text().splitlines()[1:]:
                        subprocess.run(['taskkill.exe','/PID',pid,'/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=subprocess.CREATE_NO_WINDOW)
    def test_restart_does_not_resume_when_gui_would_remain_alive(self):
        with patch.object(desktop,'RESTART_STATUS_PATH',self.status),patch.object(desktop,'RESTART_LOG_PATH',self.log):
            script=desktop.build_restart_script(0,session_root=self.root/'unused')
        # Use inert function overrides. No system process query or kill runs.
        prefix="function Get-CimInstance { [pscustomobject]@{ Name='Codex.exe'; ExecutablePath='C:\\fixture\\Codex.exe'; CommandLine=''; ProcessId=999999; ParentProcessId=0; CreationDate=1 } }\n"
        script=script.replace('\ntry {\n    Write-Log', "\nfunction Test-DesktopPath { return $true }\nfunction Invoke-HiddenTaskkill { }\ntry {\n    Write-Log",1).replace('.AddSeconds(12)','.AddSeconds(0)')
        result=self.run_script(prefix+script)
        self.assertEqual(result.returncode,1)
        self.assertEqual(json.loads(self.status.read_text(encoding='utf-8-sig'))['state'],'failed')
        self.assertNotIn('Codex Desktop GUI relaunched',self.log.read_text(encoding='utf-8-sig'))

class RestartStatusTests(unittest.TestCase):
    def app(self):
        app=CodexControlWindowsApp.__new__(CodexControlWindowsApp)
        app.root=Mock(); app._desktop_restart_busy=True; app._desktop_restart_process=Mock()
        app._desktop_restart_process.poll.return_value=None
        app._desktop_restart_started=time.monotonic(); app._quitting=False
        app._render=Mock(); app.show_window=Mock(); app._refresh_active_identity=Mock()
        return app
    def test_failure_restores_panel_with_error(self):
        app=self.app()
        with patch('pathlib.Path.read_text',return_value='{"state":"failed","detail":"Desktop did not exit"}'):
            app._check_desktop_restart()
        self.assertFalse(app._desktop_restart_busy); app.show_window.assert_called_once()
        self.assertIn('Desktop did not exit',app.status_message)
    def test_success_is_reported_only_after_helper_completion(self):
        app=self.app()
        with patch('pathlib.Path.read_text',return_value='{"state":"stopping"}'):
            app._check_desktop_restart()
        self.assertTrue(app._desktop_restart_busy); app.root.after.assert_called_once()
        with patch('pathlib.Path.read_text',return_value='{"state":"complete"}'):
            app._check_desktop_restart()
        self.assertFalse(app._desktop_restart_busy); app._refresh_active_identity.assert_called_once()
        app.show_window.assert_not_called()

class DesktopProfileTests(unittest.TestCase):
    def test_active_nested_profile_is_preferred_to_obsolete_empty_package_directory(self):
        with tempfile.TemporaryDirectory() as value:
            root=Path(value); roaming=root/'roaming'; package=root/'package'
            old=package/'LocalCache'/'Roaming'/'Codex'; old.mkdir(parents=True)
            active=roaming/'Codex'/'web'/'Codex'; active.mkdir(parents=True)
            (active/'Local State').write_text('{}'); (active/'lockfile').write_text('')
            with patch.object(file_locations,'appdata_directory',return_value=roaming),patch.object(file_locations,'codex_desktop_package_directories',return_value=[package]):
                self.assertEqual(file_locations.codex_desktop_session_root(),active)

if __name__=='__main__': unittest.main()
