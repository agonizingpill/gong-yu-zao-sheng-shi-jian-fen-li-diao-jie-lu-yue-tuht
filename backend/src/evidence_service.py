import os
import redis
from sqlalchemy import select
from fastapi import HTTPException
from .models import NoiseEvent,Separation,Attribution,Agreement,Remedy,Breach
from .common import require,lock_case,record,now,dump,within_window
queue=redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'),decode_responses=True,socket_connect_timeout=2,socket_timeout=2)
def create_event(db,user,caseid,data):
    case=lock_case(db,caseid)
    require(case.consent,'监测授权已撤回或尚未取得，不能新增频带事件')
    require(case.status!='closed','已结案，请主管先重开')
    require(data.measured_at<=now(db),'监测时间不可晚于演示时钟')
    require(not db.scalar(select(NoiseEvent).where(NoiseEvent.complaint_id==caseid,NoiseEvent.measured_at==data.measured_at,NoiseEvent.position==data.position)),'同地点同一时刻已登记事件，禁止重复计数')
    row=NoiseEvent(complaint_id=caseid,**data.model_dump(),total=sum(data.energies));db.add(row);db.flush()
    agreements=db.scalars(select(Agreement).where(Agreement.complaint_id==caseid,Agreement.state.in_(['active','observing','breached']))).all()
    for a in agreements:
        # 复发必须在整改交付之后且处于约定的静音时段。
        remedies=db.scalars(select(Remedy).where(Remedy.agreement_id==a.id)).all()
        completions=[r.completed_at for r in remedies if r.completed_at]
        if completions and data.measured_at>max(completions) and within_window(data.measured_at,a) and row.total>a.threshold:
            db.add(Breach(agreement_id=a.id,event_id=row.id));a.state='breached';case.status='remedy';a.observation_from=None;a.observation_until=None
            for r in remedies:r.state='reopened'
    record(db,user,'event.record',row.id,f'complaint={caseid};total={row.total}');db.commit();return dump(row)
def start_separation(db,user,caseid):
    case=lock_case(db,caseid);require(case.consent,'撤回监测授权后不能新增算法处理');require(case.status!='closed','已结案不能重新处理')
    events=db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==caseid).order_by(NoiseEvent.id)).all()
    require(len(events)>=3,'至少需要3条频带事件才可分离成分')
    require(not db.scalar(select(Separation).where(Separation.complaint_id==caseid,Separation.state.in_(['queued','running']))),'已有成分分离正在运行')
    job=Separation(complaint_id=caseid,event_ids=[e.id for e in events]);db.add(job);db.flush();record(db,user,'separation.queue',job.id,caseid)
    # 入列失败会使事务回滚；worker先锁投诉再锁任务，保证相同顺序。
    try:queue.rpush('quiet:separation',str(job.id))
    except redis.RedisError:raise HTTPException(503,'计算队列暂不可用，任务未创建；恢复后可重试')
    db.commit();return dump(job)
def confirm(db,user,caseid,data):
    case=lock_case(db,caseid);require(case.status!='closed','已结案不能修改归因')
    job=db.get(Separation,data.separation_id)
    require(job is not None and job.complaint_id==caseid and job.state=='done','须选择本卷已完成的成分分离')
    ids=list(db.scalars(select(NoiseEvent.id).where(NoiseEvent.complaint_id==caseid).order_by(NoiseEvent.id)))
    require(ids==job.event_ids,'频带事件已变更，请重新分离后复核')
    require(not db.scalar(select(Attribution).where(Attribution.separation_id==job.id)),'该分离记录已由人工复核')
    row=Attribution(complaint_id=caseid,separation_id=job.id,source=data.source,evidence=data.evidence,reviewer=user.username);db.add(row)
    case.status='mediation';record(db,user,'attribution.confirm',caseid,data.evidence);db.commit();return dump(row)
