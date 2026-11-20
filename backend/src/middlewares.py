import time,uuid
from collections import defaultdict,deque
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
class TraceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self,request,call_next):
        trace=uuid.uuid4().hex[:12];start=time.monotonic()
        response=await call_next(request)
        response.headers['X-Trace-Id']=trace
        response.headers['X-Elapsed-Ms']=str(round((time.monotonic()-start)*1000,1))
        response.headers['X-Content-Type-Options']='nosniff'
        return response
class LimitMiddleware(BaseHTTPMiddleware):
    def __init__(self,app): super().__init__(app);self.recent=defaultdict(deque)
    async def dispatch(self,request,call_next):
        if request.url.path=='/health': return await call_next(request)
        ip=request.client.host if request.client else 'local';key=(ip,request.url.path=='/auth/login');now=time.monotonic();q=self.recent[key]
        while q and q[0]<now-60:q.popleft()
        cap=120 if key[1] else 1200
        if len(q)>=cap:return JSONResponse({'detail':'操作频率过高，请稍后重试'},status_code=429,headers={'Retry-After':'60'})
        q.append(now)
        return await call_next(request)
