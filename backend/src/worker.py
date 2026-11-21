import os,time,json,traceback
from pathlib import Path
import redis
from sqlalchemy import select
from .database import Session
from .models import Separation,NoiseEvent
from .common import lock_case
from . import suspension_service as suspension
from .separation import calculate
q=redis.Redis.from_url(os.getenv('REDIS_URL','redis://redis:6379/0'),decode_responses=True)
while True:
    Path('/tmp/worker-heartbeat').touch()
    try:q.blpop('quiet:separation',timeout=2)
    except redis.RedisError:time.sleep(1)
    # 数据库queued为持久任务源；Redis仅唤醒，防止入列与提交之间丢任务。
    jobid=None
    try:
        with Session() as db:
            candidate=db.scalar(select(Separation).where(Separation.state=='queued').order_by(Separation.id))
            if candidate is None:continue
            case=lock_case(db,candidate.complaint_id)
            job=db.scalar(select(Separation).where(Separation.id==candidate.id).with_for_update().execution_options(populate_existing=True))
            if job.state!='queued':continue
            jobid=job.id
            if not case.consent:raise ValueError('授权已撤回，任务取消；恢复授权后可重新提交')
            job.state='running'
            # 双重保险：排队后若有采样被停用隔离，计算时再次剔除，不把停用时段数据送进NMF。
            blocked=suspension.quarantined_ids(db,job.complaint_id)
            events=[{'id':e.id,'energies':e.energies} for e in db.scalars(select(NoiseEvent).where(NoiseEvent.id.in_(job.event_ids)).order_by(NoiseEvent.id)) if e.id not in blocked]
            db.commit()
        result=calculate(events)
        with Session() as db:
            job=db.get(Separation,jobid);case=lock_case(db,job.complaint_id)
            if not case.consent:raise ValueError('授权撤回，分离结果不发布')
            job.result=result;job.state='done';db.commit()
        Path('/artifacts').mkdir(exist_ok=True)
        Path(f'/artifacts/separation-{jobid}.json').write_text(json.dumps(result,ensure_ascii=False))
    except Exception as e:
        traceback.print_exc()
        if jobid:
            with Session() as db:
                job=db.get(Separation,jobid);job.state='failed';job.error=str(e)[:400];db.commit()
