import os,hmac
from contextlib import asynccontextmanager
from fastapi import FastAPI,Depends,HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select,text
from sqlalchemy.exc import IntegrityError
from .database import Base,engine,session
from .models import User
from .auth import issue,password_hash,current
from .case_schemas import Login
from .middlewares import TraceMiddleware,LimitMiddleware
from .case_routes import router as cases
from .evidence_routes import router as evidence
from .agreement_routes import router as agreements
from .constants import ROLES,CASE_STATES,SOURCE_TYPES,BANDS
@asynccontextmanager
async def lifespan(app):
    Base.metadata.create_all(engine)
    if os.getenv('SEED_DEMO','true').lower()=='true':
        try:
            from scripts.seed_demo import seed
            seed()
        except Exception as exc:print('DEMO SEED FAILED:',str(exc))
    yield
app=FastAPI(title='栖桥 · 噪声调解簿',lifespan=lifespan)
app.add_middleware(TraceMiddleware);app.add_middleware(LimitMiddleware)
@app.exception_handler(IntegrityError)
async def conflict(request,exc):return JSONResponse({'detail':'关联记录重复或约束冲突，请刷新后重试'},status_code=409)
@app.get('/health')
def health(db=Depends(session)):
    db.execute(text('SELECT 1'));return {'status':'ok'}
@app.post('/auth/login')
def login(data:Login,db=Depends(session)):
    u=db.scalar(select(User).where(User.username==data.username))
    if not u or not hmac.compare_digest(u.password_hash,password_hash(data.password)):raise HTTPException(401,'账号或密码不正确')
    return {'token':issue(u),'user':{'username':u.username,'role':u.role}}
@app.get('/auth/me')
def me(u=Depends(current)):return {'username':u.username,'role':u.role}
@app.get('/enums')
def enums(u=Depends(current)):return {'roles':ROLES,'case_states':CASE_STATES,'source_types':SOURCE_TYPES,'bands':BANDS}
app.include_router(cases);app.include_router(evidence);app.include_router(agreements)
