from datetime import datetime,timedelta
from sqlalchemy import select,func
from src.database import Base,engine,Session
from src.models import User,DemoClock,Complaint,NoiseEvent
from src.auth import password_hash
from src import suspension_service as suspension

class _Actor:
    username='seed-demo'

def _seed_meter_case(db):
    """QT034：楼道换表后重构误差持续偏离，开箱即处于停用并带待复测采样。"""
    if db.scalar(select(Complaint).where(Complaint.code=='QT034')):return
    import numpy as np
    c=Complaint(code='QT034',alias='访客檐下',building='9栋楼道',summary='楼道换表后频带剖面漂移，验证采样停用与复测放行',consent=True,consent_note='书面授权QTC-034')
    db.add(c);db.flush()
    position='楼道换表测点B';base=datetime(2026,11,18,9,0)
    normal=[[8+j*.1,6,1.6,.5,.3,.2,.1,.05] for j in range(6)]
    drift=[[float(x) for x in r] for r in np.random.default_rng(7).uniform(4,9,size=(6,8))]
    for j,e in enumerate(normal):
        db.add(NoiseEvent(complaint_id=c.id,measured_at=base+timedelta(minutes=j*5),position=position,duration_s=60,energies=e,total=sum(e),note='换表前正常合成频带，无录音'))
    db.flush()
    # 前3条漂移触发停用并确认隔离，后3条在停用期间登记为待复测候选。
    for k,e in enumerate(drift):
        row=NoiseEvent(complaint_id=c.id,measured_at=base+timedelta(minutes=40+k*5),position=position,duration_s=60,energies=e,total=sum(e),note='换表后合成频带，无录音及真实住户信息')
        db.add(row);db.flush();suspension.screen_event(db,_Actor(),c,row)

def seed():
    Base.metadata.create_all(engine)
    with Session() as db:
        for role in ('operator','supervisor','viewer'):
            if not db.scalar(select(User).where(User.username==role)):
                db.add(User(username=role,role=role,password_hash=password_hash('Quiet2026!')))
        if not db.get(DemoClock,1):db.add(DemoClock(id=1,at=datetime(2026,11,18,16,0)))
        items=[('QT031','访客青叶','3栋北侧','22:30设备低频持续，申请协调减振时段',True),('QT032','访客杉木','6栋东侧','午间装修冲击频带，尚未授权监测',False),('QT033','访客白榆','1栋走廊','晚间人声频带事件，希望双方协调安静时段',True)]
        for code,alias,building,summary,consent in items:
            if not db.scalar(select(Complaint).where(Complaint.code==code)):
                c=Complaint(code=code,alias=alias,building=building,summary=summary,consent=consent,consent_note='书面授权QTC-031' if consent else '待取得授权');db.add(c);db.flush()
                if consent:
                    for j in range(6):
                        energy=[8+j*.1,6,1.6,.5,.3,.2,.1,.05] if code=='QT031' else [.2,.3,.8,3,6+j*.1,7,4,1]
                        db.add(NoiseEvent(complaint_id=c.id,measured_at=datetime(2026,11,17,22,30)+timedelta(minutes=j*5),position='窗台测点A',duration_s=60,energies=energy,total=sum(energy),note='合成频带示例，无录音及真实住户信息'))
        _seed_meter_case(db)
        db.commit()
        counts={m.__tablename__:db.scalar(select(func.count()).select_from(m)) for m in (User,Complaint,NoiseEvent,DemoClock)}
        print(counts)
        return counts
if __name__=='__main__':seed()
