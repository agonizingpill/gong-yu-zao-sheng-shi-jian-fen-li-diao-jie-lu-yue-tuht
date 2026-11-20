from sqlalchemy import select
from fastapi import HTTPException
from .models import Complaint,DemoClock,Audit,Agreement

def require(ok,message,code=409):
    if not ok: raise HTTPException(code,message)
def get(db,model,id):
    row=db.get(model,id)
    if not row:raise HTTPException(404,'记录不存在')
    return row
def lock_case(db,id):
    row=db.scalar(select(Complaint).where(Complaint.id==id).with_for_update().execution_options(populate_existing=True))
    if not row:raise HTTPException(404,'投诉记录不存在')
    return row
def lock_agreement(db,id):
    item=get(db,Agreement,id);case=lock_case(db,item.complaint_id)
    db.refresh(item)
    return case,item
def now(db):return get(db,DemoClock,1).at
def record(db,user,action,subject,detail=''):
    db.add(Audit(actor=user.username,action=action,subject=str(subject),detail=str(detail)))
def dump(row):
    if row is None:return None
    return {col.name:getattr(row,col.name) for col in row.__table__.columns}
def within_window(dt,agreement):
    n=dt.hour*60+dt.minute;a=agreement.quiet_from;b=agreement.quiet_to
    return a<=n<b if a<b else n>=a or n<b
