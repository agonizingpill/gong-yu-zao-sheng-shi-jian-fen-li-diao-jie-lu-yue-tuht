from datetime import timedelta
from sqlalchemy import select
from .models import Remedy,Recheck,NoiseEvent,Breach,Closure
from .common import require,lock_agreement,get,record,dump,now,within_window

def completed(db,a):
    tasks=db.scalars(select(Remedy).where(Remedy.agreement_id==a.id)).all()
    require(tasks and all(t.state=='completed' for t in tasks),'整改清单尚未全部交付')
    return tasks

def recheck(db,user,id,data):
    case,a=lock_agreement(db,id);require(a.state in ('active','breached'),'当前不可登记复验')
    tasks=completed(db,a);e=get(db,NoiseEvent,data.event_id)
    require(e.complaint_id==case.id,'复验事件必须属于本卷')
    require(e.measured_at>max(t.completed_at for t in tasks),'复验必须在最后一项整改完成之后')
    require(within_window(e.measured_at,a),'复验必须覆盖协议静音时段')
    require(not db.scalar(select(Recheck).where(Recheck.event_id==e.id)),'该事件已用作复验')
    row=Recheck(agreement_id=id,event_id=e.id,passed=e.total<=a.threshold,note=data.note);db.add(row);db.flush()
    record(db,user,'recheck.pass' if row.passed else 'recheck.fail',row.id,data.note);db.commit();return dump(row)
def resolve_breach(db,user,id,data):
    breach=get(db,Breach,id);case,a=lock_agreement(db,breach.agreement_id);db.refresh(breach)
    require(not breach.resolved,'复发记录已处理');completed(db,a)
    checks=db.scalars(select(Recheck).where(Recheck.agreement_id==a.id,Recheck.passed==True).order_by(Recheck.id.desc())).all()
    e=get(db,NoiseEvent,breach.event_id)
    require(any(get(db,NoiseEvent,c.event_id).measured_at>e.measured_at for c in checks),'须在复发后重新整改并通过静音时段复验')
    breach.resolved=True;breach.resolution=data.resolution;record(db,user,'breach.resolve',id,data.resolution);db.commit();return dump(breach)
def observe(db,user,id):
    case,a=lock_agreement(db,id);require(a.state in ('active','breached'),'当前不可启动观察期');tasks=completed(db,a)
    require(not db.scalar(select(Breach).where(Breach.agreement_id==id,Breach.resolved==False)),'仍有未解决的复发记录')
    checks=db.scalars(select(Recheck).where(Recheck.agreement_id==id).order_by(Recheck.id.desc())).all()
    require(checks and checks[0].passed,'须以最近一次通过的复验进入观察期')
    checked=get(db,NoiseEvent,checks[0].event_id)
    require(checked.measured_at>max(t.completed_at for t in tasks),'整改后须重新复验')
    a.state='observing';a.observation_from=now(db);a.observation_until=now(db)+timedelta(days=a.observation_days);case.status='observation'
    record(db,user,'observation.start',id,a.observation_until.isoformat());db.commit();return dump(a)
def close(db,user,id,note):
    case,a=lock_agreement(db,id);require(a.state=='observing','协议须处于观察期')
    require(now(db)>=a.observation_until,'观察期尚未结束，请到期后复核结案')
    require(not db.scalar(select(Breach).where(Breach.agreement_id==id,Breach.resolved==False)),'复发未解决，不能结案');completed(db,a)
    row=Closure(complaint_id=case.id,agreement_id=id,note=note,closed_at=now(db));db.add(row);a.state='fulfilled';case.status='closed'
    record(db,user,'complaint.close',case.id,note);db.commit();return dump(row)
