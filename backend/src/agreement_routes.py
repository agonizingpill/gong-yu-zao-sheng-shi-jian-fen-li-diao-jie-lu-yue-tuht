from fastapi import APIRouter,Depends
from sqlalchemy import select
from .database import session
from .auth import current,operator,supervisor
from .models import Agreement,Signature,Remedy,Recheck,Breach,Closure
from .common import dump,get
from .agreement_schemas import AgreementInput,SignatureInput,RemedyInput,ReceiptInput,RecheckInput,ResolutionInput
from .case_schemas import NoteInput
from . import agreement_service as service,resolution_service as resolution
router=APIRouter()
@router.get('/complaints/{id}/agreements')
def agreements(id:int,db=Depends(session),u=Depends(current)):
    rows=db.scalars(select(Agreement).where(Agreement.complaint_id==id).order_by(Agreement.id.desc())).all()
    return [{**dump(a),'signatures':[dump(s) for s in db.scalars(select(Signature).where(Signature.agreement_id==a.id))]} for a in rows]
@router.post('/complaints/{id}/agreements')
def draft(id:int,data:AgreementInput,db=Depends(session),u=Depends(supervisor)):return service.create_agreement(db,u,id,data)
@router.post('/agreements/{id}/signatures')
def sign(id:int,data:SignatureInput,db=Depends(session),u=Depends(operator)):return service.sign(db,u,id,data)
@router.post('/agreements/{id}/activate')
def activate(id:int,db=Depends(session),u=Depends(supervisor)):return service.activate(db,u,id)
@router.post('/agreements/{id}/cancel')
def cancel(id:int,data:NoteInput,db=Depends(session),u=Depends(supervisor)):return service.cancel(db,u,id,data.note)
@router.get('/agreements/{id}/remedies')
def remedies(id:int,db=Depends(session),u=Depends(current)):return [dump(r) for r in db.scalars(select(Remedy).where(Remedy.agreement_id==id))]
@router.post('/agreements/{id}/remedies')
def remedy(id:int,data:RemedyInput,db=Depends(session),u=Depends(operator)):return service.create_remedy(db,u,id,data)
@router.post('/remedies/{id}/complete')
def complete(id:int,data:ReceiptInput,db=Depends(session),u=Depends(operator)):return service.complete_remedy(db,u,id,data)
@router.get('/agreements/{id}/rechecks')
def checks(id:int,db=Depends(session),u=Depends(current)):return [dump(r) for r in db.scalars(select(Recheck).where(Recheck.agreement_id==id))]
@router.post('/agreements/{id}/rechecks')
def check(id:int,data:RecheckInput,db=Depends(session),u=Depends(operator)):return resolution.recheck(db,u,id,data)
@router.get('/agreements/{id}/breaches')
def breaches(id:int,db=Depends(session),u=Depends(current)):return [dump(r) for r in db.scalars(select(Breach).where(Breach.agreement_id==id))]
@router.post('/breaches/{id}/resolve')
def resolve(id:int,data:ResolutionInput,db=Depends(session),u=Depends(supervisor)):return resolution.resolve_breach(db,u,id,data)
@router.post('/agreements/{id}/observe')
def observe(id:int,db=Depends(session),u=Depends(supervisor)):return resolution.observe(db,u,id)
@router.post('/agreements/{id}/close')
def close(id:int,data:NoteInput,db=Depends(session),u=Depends(supervisor)):return resolution.close(db,u,id,data.note)
@router.get('/complaints/{id}/closures')
def closures(id:int,db=Depends(session),u=Depends(current)):return [dump(r) for r in db.scalars(select(Closure).where(Closure.complaint_id==id))]
