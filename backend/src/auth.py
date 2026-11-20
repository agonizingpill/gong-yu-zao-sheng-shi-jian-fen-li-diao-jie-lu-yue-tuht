import hashlib,hmac,os,time
import jwt
from fastapi import Depends,HTTPException
from fastapi.security import HTTPBearer
from sqlalchemy import select
from .database import session
from .models import User
security=HTTPBearer()
SECRET=os.getenv('JWT_SECRET','quiet-demo-replace-me')
def password_hash(p): return hashlib.pbkdf2_hmac('sha256',p.encode(),b'quiet-local-auth',180000).hex()
def issue(user): return jwt.encode({'sub':str(user.id),'exp':int(time.time())+28800},SECRET,algorithm='HS256')
def current(c=Depends(security),db=Depends(session)):
    try:
        claim=jwt.decode(c.credentials,SECRET,algorithms=['HS256']);u=db.get(User,int(claim['sub']))
        if not u: raise ValueError()
        return u
    except Exception: raise HTTPException(401,'登录已失效，请重新登录')
def operator(user=Depends(current)):
    if user.role not in ('operator','supervisor'): raise HTTPException(403,'只读账号不能执行业务动作')
    return user
def supervisor(user=Depends(current)):
    if user.role!='supervisor':raise HTTPException(403,'此动作需要协调主管复核')
    return user
