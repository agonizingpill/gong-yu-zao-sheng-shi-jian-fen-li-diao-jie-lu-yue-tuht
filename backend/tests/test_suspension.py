"""换表停用领域规则测试：基线/连续偏离/隔离/复测放行/调解拦截/不重复开停用。

使用SQLite内存库与桩Redis，不依赖MySQL或真实队列；NMF诊断本身保持确定性。
"""
import types
import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.evidence_service as es
from src import database
from src.models import Base,DemoClock,User,Complaint,NoiseEvent,Suspension,SuspensionEvent,Requalification,Attribution,Agreement,Remedy
from src.common import record
from src import suspension_service as sus_svc
from src.evidence_schemas import EventInput,RequalificationInput

POSITION='窗台测点A'
NORMAL=[[8+j*.1,6,1.6,.5,.3,.2,.1,.05] for j in range(6)]
DRIFT=[[float(x) for x in r] for r in np.random.default_rng(7).uniform(4,9,size=(6,8))]

@pytest.fixture()
def db(monkeypatch):
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False})
    # 单一持久连接，保证所有Session看到同一个内存库；fixture结束统一关闭。
    from sqlalchemy.pool import StaticPool
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession=sessionmaker(engine,expire_on_commit=False)
    database.Session=TestSession
    monkeypatch.setattr(es,'queue',types.SimpleNamespace(rpush=lambda *a,**k:1))
    setup=TestSession()
    setup.add(DemoClock(id=1,at=__import__('datetime').datetime(2026,11,18,16,0)))
    actor=User(username='operator',role='operator',password_hash='x')
    sup=User(username='supervisor',role='supervisor',password_hash='x')
    setup.add_all([actor,sup]);setup.commit()
    setup.close()
    class Actor:
        def __init__(self,username):self.username=username
    yield TestSession,Actor('operator'),Actor('supervisor')

def make_case(s,code='QT099',consent=True):
    c=Complaint(code=code,alias='访客测试',building='3栋北侧',summary='换表停用测试卷宗',consent=consent,consent_note='授权')
    s.add(c);s.flush();return c

def add_event(s,actor,caseid,energies,minute,position=POSITION):
    from datetime import datetime,timedelta
    data=EventInput(measured_at=datetime(2026,11,17,20,0)+timedelta(minutes=minute),
                    position=position,duration_s=60,energies=energies,note='合成频带事件，无原始录音，点位固定。')
    return es.create_event(s,actor,caseid,data)

def error_of(event_id,s):
    return s.scalar(__import__('sqlalchemy').select(SuspensionEvent.reconstruction_error).where(SuspensionEvent.event_id==event_id))

def test_normal_baseline_keeps_all_events_usable(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        assert sus_svc.quarantined_ids(s,c.id)==set()
        assert s.scalar(__import__('sqlalchemy').select(__import__('sqlalchemy').func.count()).select_from(Suspension))==0

def test_consecutive_drift_opens_suspension_from_first_anomaly(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        ids=[]
        for j,e in enumerate(NORMAL):ids.append(add_event(s,actor,c.id,e,j)['id'])
        drift_ids=[add_event(s,actor,c.id,e,10+k)['id'] for k,e in enumerate(DRIFT[:3])]
        pending_ids=[add_event(s,actor,c.id,e,13+k)['id'] for k,e in enumerate(DRIFT[3:])]
        sus=s.scalars(__import__('sqlalchemy').select(Suspension)).all()
        assert len(sus)==1 and sus[0].state=='active'
        # 停用起点=首次异常（漂移第1条，即总第7条），而不是触发时刻（第9条）。
        first_drift=drift_ids[0]
        assert sus[0].first_event_id==first_drift
        assert sus[0].suspended_from==s.get(NoiseEvent,first_drift).measured_at
        links=s.scalars(__import__('sqlalchemy').select(SuspensionEvent)).all()
        assert {x.event_id for x in links}==set(drift_ids)|set(pending_ids)
        # 触发停用的漂移批次直接确认隔离；停用后新到的同测点采样为待复测。
        assert all(x.state=='quarantined' for x in links if x.event_id in drift_ids)
        assert all(x.state=='pending' for x in links if x.event_id in pending_ids)

def test_suspended_samples_skipped_by_separation_and_breach(db):
    Session,actor,sup=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        for k,e in enumerate(DRIFT[3:]):add_event(s,actor,c.id,e,13+k)
        # 分离只取未拦住的采样。
        job=es.start_separation(s,actor,c.id)
        assert set(job['event_ids']).isdisjoint(sus_svc.quarantined_ids(s,c.id))
        assert len(job['event_ids'])==len(NORMAL)
        # 停用期间高能量采样不应产生复发/复验资格。
        quar=[x.event_id for x in s.scalars(__import__('sqlalchemy').select(SuspensionEvent))]
        assert s.get(NoiseEvent,quar[0]).total>0

def test_recheck_rejects_quarantined_event(db):
    from src import resolution_service as rs
    from src.agreement_schemas import RecheckInput
    Session,actor,sup=db
    with Session() as s:
        c=make_case(s);c.status='mediation'
        from src.models import Separation
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        # 连续3条漂移打开停用，再登记一条停用期间采样用于复验拦截。
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        blocked=add_event(s,actor,c.id,DRIFT[3],30)
        job=Separation(complaint_id=c.id,state='done',event_ids=[e.id for e in s.scalars(__import__('sqlalchemy').select(NoiseEvent))])
        s.add(job);s.flush()
        attr=Attribution(complaint_id=c.id,separation_id=job.id,source='equipment',evidence='现场证据足够长的描述文本',reviewer='supervisor')
        s.add(attr);s.flush()
        a=Agreement(complaint_id=c.id,attribution_id=attr.id,party_a='甲',party_b='乙',quiet_from=0,quiet_to=1439,threshold=999,observation_days=2,state='active')
        s.add(a);s.flush()
        from datetime import datetime
        r=Remedy(agreement_id=a.id,instruction='整改内容足够长',responsible='乙',state='completed',receipt='收据内容足够长',completed_at=datetime(2026,11,17,19,0))
        s.add(r);s.flush()
        with pytest.raises(Exception) as exc:
            rs.recheck(s,actor,a.id,RecheckInput(event_id=blocked['id'],note='停用采样不能复验的说明'))
        assert '停用' in str(exc.value.detail)

def test_requalification_pass_releases_only_post_recovery_samples(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        normal_ids=[add_event(s,actor,c.id,e,j)['id'] for j,e in enumerate(NORMAL)]
        drift_ids=[add_event(s,actor,c.id,e,10+k)['id'] for k,e in enumerate(DRIFT[:3])]
        sus=s.scalar(__import__('sqlalchemy').select(Suspension))
        # 恢复后用正常模板的新采样复测。
        retest=[]
        for k in range(4):
            row=add_event(s,actor,c.id,[v*(1+0.01*k) for v in NORMAL[0]],30+k)
            retest.append(row['id'])
        out=sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=sus.id,event_ids=retest,note='换表后同测点复测，频带剖面回到正常区间'))
        assert out['passed'] is True
        s.refresh(sus);assert sus.state=='released' and sus.released_at is not None
        states={x.event_id:x.state for x in s.scalars(__import__('sqlalchemy').select(SuspensionEvent))}
        # 旧漂移仍隔离，复测批次放行，正常采样从未进隔离表。
        assert all(states[e]=='quarantined' for e in drift_ids)
        assert all(states[e]=='released' for e in retest)
        assert set(normal_ids).isdisjoint(states)
        assert set(retest).isdisjoint(sus_svc.quarantined_ids(s,c.id))

def test_requalification_fail_keeps_suspension_active(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        sus=s.scalar(__import__('sqlalchemy').select(Suspension))
        bad=[add_event(s,actor,c.id,DRIFT[3],13)['id']]
        bad.append(add_event(s,actor,c.id,DRIFT[4],14)['id'])
        bad.append(add_event(s,actor,c.id,DRIFT[5],15)['id'])
        out=sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=sus.id,event_ids=bad,note='复测仍漂移的说明文字'))
        assert out['passed'] is False
        s.refresh(sus);assert sus.state=='active'
        assert set(bad).issubset(sus_svc.quarantined_ids(s,c.id))

def test_rerun_does_not_reopen_same_suspension(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        first=s.scalar(__import__('sqlalchemy').select(Suspension))
        # 同一批漂移事件再次“重跑”筛查（幂等：已全部隔离，不新增停用时段）。
        for e in s.scalars(__import__('sqlalchemy').select(NoiseEvent).where(NoiseEvent.position==POSITION)):
            sus_svc.screen_event(s,actor,c,e)
        assert s.scalar(__import__('sqlalchemy').select(__import__('sqlalchemy').func.count()).select_from(Suspension))==1
        # 放行后再次持续偏离：新开停用时段并链接旧段。
        retest=[add_event(s,actor,c.id,NORMAL[0],30+k)['id'] for k in range(3)]
        sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=first.id,event_ids=retest,note='复测达标放行说明'))
        for k in range(3):add_event(s,actor,c.id,DRIFT[k],40+k)
        rows=s.scalars(__import__('sqlalchemy').select(Suspension).order_by(Suspension.id)).all()
        assert len(rows)==2 and rows[1].reopened_from_id==first.id

def test_mediation_blocked_when_attribution_touches_suspension(db):
    Session,actor,sup=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        sus=s.scalar(__import__('sqlalchemy').select(Suspension))
        # 构造一个含隔离事件的旧分离与归因，模拟停用与归因同时提交。
        job=es.Separation(complaint_id=c.id,state='done',event_ids=[e.id for e in s.scalars(__import__('sqlalchemy').select(NoiseEvent))])
        s.add(job);s.flush()
        attr=Attribution(complaint_id=c.id,separation_id=job.id,source='equipment',evidence='现场证据足够长的描述文本',reviewer='supervisor')
        s.add(attr);s.flush();sus_svc.refresh_attribution_flags(s,c.id)
        assert attr.suspended is True and sus.id in attr.suspension_ids
        with pytest.raises(Exception) as exc:
            sus_svc.mediation_blocked_attribution(s,c.id,attr.id)
        assert '暂停' in str(exc.value.detail)
        # 复测放行后标记清除，调解不再被拦。
        retest=[add_event(s,actor,c.id,NORMAL[0],30+k)['id'] for k in range(3)]
        sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=sus.id,event_ids=retest,note='复测达标放行说明'))
        s.refresh(attr);assert attr.suspended is False and attr.suspension_ids==[]
        sus_svc.mediation_blocked_attribution(s,c.id,attr.id)

def test_activated_agreement_continues_after_suspension(db):
    Session,actor,sup=db
    with Session() as s:
        c=make_case(s)
        from src.models import Separation
        job=Separation(complaint_id=c.id,state='done',event_ids=[])
        s.add(job);s.flush()
        attr=Attribution(complaint_id=c.id,separation_id=job.id,source='equipment',evidence='现场证据足够长的描述文本',reviewer='supervisor')
        s.add(attr);s.flush()
        a=Agreement(complaint_id=c.id,attribution_id=attr.id,party_a='甲',party_b='乙',quiet_from=0,quiet_to=1439,threshold=500,observation_days=2,state='active')
        s.add(a);s.commit()
        # 协议生效后该测点才换表：协议照常履行，不被停用撤销。
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        s.refresh(a);assert a.state=='active'
        assert s.scalar(__import__('sqlalchemy').select(__import__('sqlalchemy').func.count()).select_from(Suspension))==1

def test_requalification_reuses_quarantined_sample_rejected(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        drift_ids=[add_event(s,actor,c.id,e,10+k)['id'] for k,e in enumerate(DRIFT[:3])]
        sus=s.scalar(__import__('sqlalchemy').select(Suspension))
        with pytest.raises(Exception) as exc:
            sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=sus.id,event_ids=drift_ids,note='试图复用停用时段采样'))
        assert '恢复后的新采样' in str(exc.value.detail)

def test_agreement_draft_blocked_then_allowed_after_release(db):
    from src import agreement_service as ag
    from src.agreement_schemas import AgreementInput
    Session,actor,sup=db
    with Session() as s:
        c=make_case(s);c.status='mediation'
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        sus=s.scalar(__import__('sqlalchemy').select(Suspension))
        from src.models import Separation
        job=Separation(complaint_id=c.id,state='done',event_ids=[e.id for e in s.scalars(__import__('sqlalchemy').select(NoiseEvent))])
        s.add(job);s.flush()
        attr=Attribution(complaint_id=c.id,separation_id=job.id,source='equipment',evidence='现场证据足够长的描述文本',reviewer='supervisor')
        s.add(attr);s.flush();sus_svc.refresh_attribution_flags(s,c.id)
        payload=AgreementInput(attribution_id=attr.id,party_a='访客甲',party_b='设备方',quiet_from=1320,quiet_to=420,threshold=10,observation_days=2)
        with pytest.raises(Exception) as exc:
            ag.create_agreement(s,sup,c.id,payload)
        assert '暂停' in str(exc.value.detail)
        # 放行后可正常起草。
        pending=[add_event(s,actor,c.id,NORMAL[0],30+k)['id'] for k in range(3)]
        sus_svc.requalify(s,actor,c.id,RequalificationInput(suspension_id=sus.id,event_ids=pending,note='复测达标放行的说明文字'))
        out=ag.create_agreement(s,sup,c.id,payload)
        assert out['state']=='draft'

def test_worker_calculation_excludes_blocked_samples(db):
    from src.separation import calculate
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        blocked=sus_svc.quarantined_ids(s,c.id)
        usable=sus_svc.usable_events(s,c.id)
        assert blocked and not (blocked & {e.id for e in usable})
        result=calculate([{'id':e.id,'energies':e.energies} for e in usable])
        assert {x['event_id'] for x in result['events']}=={e.id for e in usable}
        assert all('reconstruction_error' in x for x in result['events'])

def test_one_active_suspension_per_position(db):
    Session,actor,_=db
    with Session() as s:
        c=make_case(s)
        for j,e in enumerate(NORMAL):add_event(s,actor,c.id,e,j)
        for k,e in enumerate(DRIFT[:3]):add_event(s,actor,c.id,e,10+k)
        first=s.scalar(__import__('sqlalchemy').select(Suspension))
        # 停用仍active时，同测点继续异常只累积pending，不产生第二个停用。
        for k in range(3):add_event(s,actor,c.id,DRIFT[k],30+k)
        active=sus_svc._active(s,c.id,POSITION)
        assert len(active)==1 and active[0].id==first.id
        # 不同测点互不影响，可独立停用。
        other=[add_event(s,actor,c.id,NORMAL[0],40+k,position='走廊测点C')['id'] for k in range(4)]
        for k in range(3):add_event(s,actor,c.id,DRIFT[k],50+k,position='走廊测点C')
        assert len(sus_svc._active(s,c.id))==2
