from sqlalchemy import select,func
from .models import Complaint,NoiseEvent,Agreement,Audit,DemoClock
from .common import require,lock_case,get,record,now,dump

def list_cases(db):
    rows=db.scalars(select(Complaint).order_by(Complaint.id)).all()
    return [{**dump(c),'event_count':db.scalar(select(func.count()).select_from(NoiseEvent).where(NoiseEvent.complaint_id==c.id))} for c in rows]
def create_case(db,user,data):
    require(not db.scalar(select(Complaint).where(Complaint.code==data.code)),'投诉编号重复')
    row=Complaint(**data.model_dump(),consent_note='来访已授权' if data.consent else '未授权，仅建卷');db.add(row);db.flush()
    record(db,user,'complaint.create',row.id,data.code);db.commit();return dump(row)
def consent(db,user,id,data):
    case=lock_case(db,id);require(case.status!='closed','已结案卷宗请先重开')
    case.consent=data.granted;case.consent_note=data.note
    record(db,user,'consent.grant' if data.granted else 'consent.withdraw',id,data.note);db.commit();return dump(case)
def advance(db,user,data):
    clock=db.scalar(select(DemoClock).where(DemoClock.id==1).with_for_update().execution_options(populate_existing=True))
    require(data.at>=clock.at,'演示时钟只能向前推进')
    clock.at=data.at;record(db,user,'clock.advance',1,data.at.isoformat());db.commit();return {'at':clock.at}
def reopen(db,user,id,note):
    case=lock_case(db,id);require(case.status=='closed','只可重开已结案投诉')
    case.status='monitoring';record(db,user,'complaint.reopen',id,note);db.commit();return dump(case)
