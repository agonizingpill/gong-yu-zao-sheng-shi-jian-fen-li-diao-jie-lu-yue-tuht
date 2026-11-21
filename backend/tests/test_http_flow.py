"""HTTP端到端：登录→事件→停用→分离→复测放行→调解拦截/恢复，使用TestClient+SQLite。"""
import types
from datetime import datetime,timedelta
import numpy as np
from fastapi.testclient import TestClient
from sqlalchemy import create_engine,select
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker

from src import database
from src.models import Base
import src.evidence_service as es

engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
Base.metadata.create_all(engine)
S=sessionmaker(engine,expire_on_commit=False);database.Session=S
es.queue=types.SimpleNamespace(rpush=lambda *a,**k:1)
from src.app import app
from src.models import DemoClock,User
from src.auth import password_hash
with S() as s:
    s.add(DemoClock(id=1,at=datetime(2026,11,18,16,0)))
    for name,role in (('operator','operator'),('supervisor','supervisor'),('viewer','viewer')):
        s.add(User(username=name,role=role,password_hash=password_hash('Quiet2026!')))
    s.commit()

client=TestClient(app)
def token(role):
    r=client.post('/auth/login',json={'username':role,'password':'Quiet2026!'});assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['token']}
OP,SUP,VIEW=token('operator'),token('supervisor'),token('viewer')
NORMAL=[[8+j*.1,6,1.6,.5,.3,.2,.1,.05] for j in range(6)]
DRIFT=[[float(x) for x in r] for r in np.random.default_rng(7).uniform(4,9,size=(6,8))]

def event(cid,e,minute,headers=OP):
    body={'measured_at':(datetime(2026,11,17,20,0)+timedelta(minutes=minute)).strftime('%Y-%m-%dT%H:%M:%S'),
          'position':'窗台测点A','duration_s':60,'energies':e,'note':'合成频带事件，无原始录音，点位固定。'}
    r=client.post(f'/complaints/{cid}/events',json=body,headers=headers);assert r.status_code==200,r.text
    return r.json()

# 1 建卷（operator）
r=client.post('/complaints',json={'code':'QT100','alias':'访客端到端','building':'3栋北侧','summary':'端到端换表停用验证卷宗内容','consent':True},headers=OP)
assert r.status_code==200,r.text;cid=r.json()['id']
# viewer写接口403
assert client.post(f'/complaints/{cid}/events',json={},headers=VIEW).status_code==403
# 2 正常采样
for j,e in enumerate(NORMAL):event(cid,e,j)
# 3 三条漂移触发停用
for k,e in enumerate(DRIFT[:3]):event(cid,e,10+k)
r=client.get(f'/complaints/{cid}/suspensions',headers=OP);sus=r.json()
assert len(sus)==1 and sus[0]['state']=='active',sus
sid=sus[0]['id']
# 停用期间再到3条采样（pending候选）
pending=[event(cid,DRIFT[3],13)['id'],event(cid,DRIFT[4],14)['id'],event(cid,DRIFT[5],15)['id']]
ev=client.get(f'/complaints/{cid}/events',headers=OP).json()
flagged={x['id']:x for x in ev if x['quarantined']}
assert set(flagged)==set(pending)|set(sus[0]['events'][i]['event_id'] for i in range(3))
assert all(flagged[i]['quarantine_state']=='quarantined' for i in [x['event_id'] for x in sus[0]['events'] if x['state']=='quarantined'])
# 4 分离自动排除被拦采样：同步跑worker逻辑（直接调用calculate路径由worker覆盖），这里验证排队任务只含可用事件
r=client.post(f'/complaints/{cid}/separations',headers=OP);assert r.status_code==200,r.text
job=r.json();blocked=set(flagged)
assert set(job['event_ids']).isdisjoint(blocked) and len(job['event_ids'])==6
# 5 复测失败：用pending里的漂移候选（它们误差高）→ 转隔离，停用仍active
r=client.post(f'/complaints/{cid}/requalifications',json={'suspension_id':sid,'event_ids':pending,'note':'首次复测频带剖面仍偏离基线的说明'},headers=OP)
assert r.status_code==200 and r.json()['passed'] is False
st=client.get(f'/complaints/{cid}/suspensions',headers=OP).json()[0]
assert st['state']=='active' and all(x['state']=='quarantined' for x in st['events'] if x['event_id'] in pending)
# 6 恢复后正常采样（pending），复测达标放行
recover=[event(cid,[v*(1+0.01*k) for v in NORMAL[0]],30+k)['id'] for k in range(4)]
r=client.post(f'/complaints/{cid}/requalifications',json={'suspension_id':sid,'event_ids':recover,'note':'换表后同测点复测剖面回到正常区间'},headers=OP)
assert r.status_code==200 and r.json()['passed'] is True,r.text
st=client.get(f'/complaints/{cid}/suspensions',headers=OP).json()[0]
assert st['state']=='released' and st['released_at']
assert {x['event_id']:x['state'] for x in st['events'] if x['event_id'] in recover}=={i:'released' for i in recover}
# 放行后这些采样在事件接口恢复可用（不再标记拦截），可重新进入分离
after={x['id']:x for x in client.get(f'/complaints/{cid}/events',headers=OP).json()}
assert all(after[i]['quarantined'] is False and after[i]['quarantine_state']=='released' for i in recover)
# 7 重跑同一恢复批次不重复开停用（再登记相同能量但新时刻不会新开；这里验证只有一个停用记录）
assert len(client.get(f'/complaints/{cid}/suspensions',headers=OP).json())==1
# 8 放行后新漂移连续3条 → 新开停用并链接旧段
for k in range(3):event(cid,DRIFT[k],40+k)
lst=client.get(f'/complaints/{cid}/suspensions',headers=OP).json()
assert len(lst)==2 and lst[0]['reopened_from_id']==sid
print('HTTP END-TO-END OK; suspension chain:',[(x['id'],x['state'],x['reopened_from_id']) for x in lst])
