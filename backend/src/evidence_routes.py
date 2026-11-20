from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import session
from .auth import current,operator,supervisor
from .models import NoiseEvent,Separation,Attribution
from .common import dump,get
from .evidence_schemas import EventInput,AttributionInput
from . import evidence_service as service
router=APIRouter()
@router.get('/complaints/{id}/events')
def events(id:int,db=Depends(session),u=Depends(current)):return [dump(x) for x in db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==id).order_by(NoiseEvent.measured_at))]
@router.post('/complaints/{id}/events')
def event(id:int,data:EventInput,db=Depends(session),u=Depends(operator)):return service.create_event(db,u,id,data)
@router.get('/complaints/{id}/separations')
def separations(id:int,db=Depends(session),u=Depends(current)):return [dump(x) for x in db.scalars(select(Separation).where(Separation.complaint_id==id).order_by(Separation.id.desc()))]
@router.post('/complaints/{id}/separations')
def separate(id:int,db=Depends(session),u=Depends(operator)):return service.start_separation(db,u,id)
@router.get('/complaints/{id}/attributions')
def attributions(id:int,db=Depends(session),u=Depends(current)):return [dump(x) for x in db.scalars(select(Attribution).where(Attribution.complaint_id==id).order_by(Attribution.id.desc()))]
@router.post('/complaints/{id}/attributions')
def attribution(id:int,data:AttributionInput,db=Depends(session),u=Depends(supervisor)):return service.confirm(db,u,id,data)
