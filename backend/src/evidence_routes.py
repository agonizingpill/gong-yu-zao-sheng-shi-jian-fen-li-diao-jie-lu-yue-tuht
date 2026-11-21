from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import session
from .auth import current,operator,supervisor
from .models import NoiseEvent,Separation,Attribution,Suspension,SuspensionEvent
from .suspension_service import BLOCKED_STATES
from .common import dump
from .evidence_schemas import EventInput,AttributionInput,RequalificationInput
from . import evidence_service as service,suspension_service as suspension
router=APIRouter()
def _event_payload(db,x):
    item=dump(x)
    link=db.scalar(select(SuspensionEvent).where(SuspensionEvent.event_id==x.id))
    # released 已放行、恢复可用，不再标记为拦截；只有 quarantined/pending 算拦住。
    item['quarantined']=link is not None and link.state in BLOCKED_STATES
    item['suspension_id']=link.suspension_id if link else None
    item['quarantine_state']=link.state if link else None
    return item
@router.get('/complaints/{id}/events')
def events(id:int,db=Depends(session),u=Depends(current)):
    return [_event_payload(db,x) for x in db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==id).order_by(NoiseEvent.measured_at))]
@router.post('/complaints/{id}/events')
def event(id:int,data:EventInput,db=Depends(session),u=Depends(operator)):
    row=service.create_event(db,u,id,data)
    return _event_payload(db,db.get(NoiseEvent,row['id']))
@router.get('/complaints/{id}/separations')
def separations(id:int,db=Depends(session),u=Depends(current)):return [dump(x) for x in db.scalars(select(Separation).where(Separation.complaint_id==id).order_by(Separation.id.desc()))]
@router.post('/complaints/{id}/separations')
def separate(id:int,db=Depends(session),u=Depends(operator)):return service.start_separation(db,u,id)
@router.get('/complaints/{id}/attributions')
def attributions(id:int,db=Depends(session),u=Depends(current)):return [dump(x) for x in db.scalars(select(Attribution).where(Attribution.complaint_id==id).order_by(Attribution.id.desc()))]
@router.post('/complaints/{id}/attributions')
def attribution(id:int,data:AttributionInput,db=Depends(session),u=Depends(supervisor)):return service.confirm(db,u,id,data)
@router.get('/complaints/{id}/suspensions')
def suspensions(id:int,db=Depends(session),u=Depends(current)):return suspension.list_payload(db,id)
@router.post('/complaints/{id}/requalifications')
def requalify(id:int,data:RequalificationInput,db=Depends(session),u=Depends(operator)):return suspension.requalify(db,u,id,data)
