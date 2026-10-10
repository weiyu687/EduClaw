import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.security.manual_replan import ReplanStore,completed_prefix,validate_replacement

OLD=[{'tool':'extract_pdf','arguments':{'pdf_path':'x'}},{'tool':'run_python_code','arguments':{'code':'print(1)'}}]
NEW=[OLD[0],{'tool':'run_python_code','arguments':{'code':'print(2)'}}]

class Snap:
    def __init__(self,idx,status='running',next=('gate',)):
        self.values={'status':status,'index':idx,'results':[{'status':'completed'}]*idx}
        self.next=next
class Results:
    def __init__(self,status='completed',truncated=False): self.status=status;self.truncated=truncated
    def get(self,*args): return {'status':self.status,'truncated':self.truncated}
class Ledger:
    def __init__(self,prefix):self.prefix=prefix
    def status(self,s,t,i):return 'completed' if i<self.prefix else None

def test_store_lifecycle(tmp_path):
    db=ReplanStore(tmp_path/'replans.db')
    rid=db.create('s','task','goal',1,NEW)
    assert db.pending_for('s','task')==rid
    assert db.get('s',rid)['prefix']==1
    with pytest.raises(Exception):db.get('other',rid)
    with pytest.raises(Exception):db.create('s','task','goal',1,NEW)
    db.transition('s',rid,'committing')
    assert db.pending_for('s','task') is None
    db.finish_commit('s',rid,'next')
    assert db.get('s',rid)['successor']=='next'
    with pytest.raises(PermissionError):db.transition('s',rid,'denied')

def test_reject_changed_prefix():
    assert validate_replacement(OLD,NEW,1)
    with pytest.raises(PermissionError):validate_replacement(OLD,[{'tool':'extract_pdf','arguments':{'pdf_path':'other'}},NEW[1]],1)
    with pytest.raises(ValueError):validate_replacement(OLD,OLD,1)


def test_store_releases_windows_file_handle(tmp_path):
    path = tmp_path / 'replans.db'
    store = ReplanStore(path)
    rid = store.create('s', 't', 'goal', 1, NEW)
    store.get('s', rid)
    store.pending_for('s', 't')
    store.transition('s', rid, 'denied')
    path.unlink()  # Windows refuses this while any SQLite connection is open.

def test_completed_prefix():
    assert completed_prefix('s','t',Snap(1),Results(),Ledger(1))==1
    with pytest.raises(PermissionError):completed_prefix('s','t',Snap(1),Results('uncertain'),Ledger(1))
    with pytest.raises(PermissionError):completed_prefix('s','t',Snap(1),Results(truncated=True),Ledger(1))
    with pytest.raises(PermissionError):completed_prefix('s','t',Snap(1,status='denied'),Results(),Ledger(1))
    with pytest.raises(PermissionError):completed_prefix('s','t',Snap(1),Results(),Ledger(0))
