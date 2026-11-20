from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import session
from .auth import current,operator,supervisor
from .models import Audit
from .common import dump,now
from .case_schemas import ComplaintInput,ConsentInput,ClockInput,NoteInput
from . import case_service as service
router=APIRouter()
@router.get('/complaints')
def cases(db=Depends(session),u=Depends(current)):return service.list_cases(db)
@router.post('/complaints')
def create(data:ComplaintInput,db=Depends(session),u=Depends(operator)):return service.create_case(db,u,data)
@router.post('/complaints/{id}/consent')
def consent(id:int,data:ConsentInput,db=Depends(session),u=Depends(operator)):return service.consent(db,u,id,data)
@router.post('/complaints/{id}/reopen')
def reopen(id:int,data:NoteInput,db=Depends(session),u=Depends(supervisor)):return service.reopen(db,u,id,data.note)
@router.get('/clock')
def clock(db=Depends(session),u=Depends(current)):return {'at':now(db)}
@router.post('/clock')
def clock_advance(data:ClockInput,db=Depends(session),u=Depends(supervisor)):return service.advance(db,u,data)
@router.get('/audit')
def audit(db=Depends(session),u=Depends(supervisor)):return [dump(x) for x in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(200))]
