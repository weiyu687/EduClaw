"""Real Windows terminal Agent consumes an active domain and its library."""
import json
import secrets
import tempfile
import time
from pathlib import Path
from windows_e2e import ROOT
from core.state.manager import StateManager
from core.state.experts import Experts,FIELDS,templates
from core.state.library import Library
from core.terminal.broker import Runtime

def main():
    with tempfile.TemporaryDirectory(prefix='educlaw-domain-terminal-') as folder:
        work=Path(folder);StateManager(work/'educlaw_state.sqlite3').ensure_session('domain-terminal')
        experts=Experts(work);profile={k:v for k,v in templates()[1].items() if k in FIELDS}
        profile.update(id='terminal-domain',prompt='最终总结必须以“工程验收”开头。请依据真实终端输出确认任务。')
        did=Library(work).add('domain-terminal','acceptance.md','测试要求：终端测试标记是 DOMAIN_TERMINAL_742。'.encode())['id']
        profile['documents']=[did];experts.save('domain-terminal',profile);experts.use('domain-terminal',profile['id'])
        runtime=Runtime(work)
        try:
            tid=runtime.call('domain-terminal','open',cwd=str(work),trust=True,confirmation='OPEN',request_id=secrets.token_hex(16))['id']
            runtime.call('domain-terminal','agent',id=tid,goal='依据领域资料中的测试标记，在终端用 Write-Output 输出该标记，核对实际输出后结束。不修改文件。',request_id=secrets.token_hex(16))
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                row=runtime.call('domain-terminal','read',id=tid)
                if row['agent']['status'] in ('completed','failed','waiting','needs_attention'):break
                time.sleep(.25)
            assert row['agent']['status']=='completed',row['agent']['status']
            assert 'DOMAIN_TERMINAL_742' in row['output'] and '工程验收' in row['agent']['answer']
            report={'real_windows_terminal':True,'real_model':True,'domain_guidance':True,'domain_library':True,'completed':True}
        finally:
            for terminal in runtime.terminals.values():terminal.close()
    (ROOT/'logs'/'expert_terminal_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report))

if __name__=='__main__':main()
