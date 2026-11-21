"""换表/漂移停用领域逻辑。

楼道换表后NMF仍会给出看似可信的成分占比，因此以各测点正常采样的逐事件
相对重构误差建立稳健基线（中位数+MAD），连续偏离即从首次异常起停用该测点
该时段的采样。停用期间采样以pending拦住不进分离、不作复验/复发，调解暂停引用
受影响归因；复测达标只放行恢复后的采样（released），失败则确认隔离，
重跑不会重复打开同一停用时段。
"""
import numpy as np
from sqlalchemy import select
from .models import (NoiseEvent,Suspension,SuspensionEvent,Requalification,
                     Separation,Attribution)
from .separation import diagnose
from .common import require,record,dump,now,lock_case

MIN_BASELINE=3          # 建立基线至少需要的正常采样
CONSECUTIVE_LIMIT=3     # 连续偏离达到该次数即停用
MAD_K=3.0
MAD_SCALE=1.4826
EPS=1e-6
# SuspensionEvent状态：
#  quarantined=已确认隔离（触发停用的漂移批次/复测失败批次），永不进业务；
#  pending=停用生效期间的新采样，先拦住，等待复测判定；
#  released=复测达标后放行，只放行恢复后的采样。
BLOCKED_STATES=('quarantined','pending')

def _cutoff(values):
    arr=np.asarray(values,dtype=float)
    median=float(np.median(arr));mad=float(np.median(np.abs(arr-median)))
    return median,mad,median+MAD_K*MAD_SCALE*mad+EPS

def _errors(db,events):
    if not events:return {}
    diag=diagnose([{'id':e.id,'energies':e.energies} for e in events])
    return {row['event_id']:row['reconstruction_error'] for row in diag['events']}

def _active(db,caseid,position=None):
    q=select(Suspension).where(Suspension.complaint_id==caseid,Suspension.state=='active')
    if position is not None:q=q.where(Suspension.position==position)
    return db.scalars(q).all()

def quarantined_ids(db,caseid):
    """本卷当前被拦住的事件id（已隔离或待复测，均不得进入业务流程）。"""
    sus=db.scalars(select(Suspension.id).where(Suspension.complaint_id==caseid)).all()
    if not sus:return set()
    return set(db.scalars(select(SuspensionEvent.event_id).where(
        SuspensionEvent.suspension_id.in_(sus),SuspensionEvent.state.in_(BLOCKED_STATES))).all())

def usable_events(db,caseid):
    blocked=quarantined_ids(db,caseid)
    return [e for e in db.scalars(select(NoiseEvent).where(NoiseEvent.complaint_id==caseid).order_by(NoiseEvent.id)).all() if e.id not in blocked]

def screen_event(db,actor,case,row):
    """事件落库后的换表筛查。返回True表示该事件被停用拦住。

    调用方已持有投诉行锁；全部写操作随调用方事务提交。
    """
    active=_active(db,case.id,row.position)
    if active:
        # 停用生效期间同测点采样先以pending拦住并留待复测，不直接判为隔离；
        # 重跑同一批数据（已登记链接）不会重复打开停用时段。
        exists=db.scalar(select(SuspensionEvent).where(SuspensionEvent.event_id==row.id))
        if exists is None:
            err=_errors(db,[row])[row.id]
            db.add(SuspensionEvent(suspension_id=active[0].id,event_id=row.id,
                                   reconstruction_error=err,state='pending'))
            record(db,actor,'suspension.pending',row.id,f'suspension={active[0].id};error={err:.5f}')
        return True
    # 基线只取该测点未被任何停用隔离的正常采样（恢复后采用新基线）。
    blocked=quarantined_ids(db,case.id)
    history=[e for e in db.scalars(select(NoiseEvent).where(
        NoiseEvent.complaint_id==case.id,NoiseEvent.position==row.position).order_by(NoiseEvent.id)).all()
        if e.id not in blocked]
    if len(history)<MIN_BASELINE:return False
    errors=_errors(db,history)
    ordered=sorted(history,key=lambda e:e.id)
    baseline=[e for e in ordered[:-1]] if len(ordered)>MIN_BASELINE else ordered
    median,mad,cutoff=_cutoff([errors[e.id] for e in baseline])
    run=[]
    for e in reversed(ordered):
        if errors[e.id]>cutoff:run.append(e)
        else:break
    if len(run)<CONSECUTIVE_LIMIT:return False
    run=sorted(run,key=lambda e:e.id);first=run[0]
    sus=Suspension(complaint_id=case.id,position=row.position,first_event_id=first.id,
                   suspended_from=first.measured_at,baseline_median=median,baseline_mad=mad,cutoff=cutoff,
                   reason=f'连续{len(run)}条采样重构误差高于基线切点{cutoff:.5f}，疑似楼道换表/设备漂移')
    db.add(sus);db.flush()
    # 恢复后再次偏离会新开停用时段并链接上一段，重跑不重复打开同一停用时段。
    prior=db.scalar(select(Suspension).where(Suspension.complaint_id==case.id,
        Suspension.position==row.position,Suspension.state=='released').order_by(Suspension.id.desc()))
    if prior:sus.reopened_from_id=prior.id
    for e in run:
        db.add(SuspensionEvent(suspension_id=sus.id,event_id=e.id,reconstruction_error=errors[e.id]))
    record(db,actor,'suspension.open',sus.id,f'position={row.position};first_event={first.id};cutoff={cutoff:.5f}')
    refresh_attribution_flags(db,case.id)
    return True

def requalify(db,user,caseid,data):
    """复测：用恢复后的采样重建基线并判定是否达标；达标只放行恢复后的采样。"""
    case=lock_case(db,caseid)
    sus=db.get(Suspension,data.suspension_id)
    require(sus is not None and sus.complaint_id==caseid,'停用记录不存在或不属于本卷',404)
    require(sus.state=='active','该停用时段已放行，不能重复复测')
    ids=list(dict.fromkeys(data.event_ids))
    require(len(ids)>=MIN_BASELINE,f'复测至少需要{MIN_BASELINE}条恢复后的采样')
    events=list(db.scalars(select(NoiseEvent).where(NoiseEvent.id.in_(ids)).order_by(NoiseEvent.id)))
    require(len(events)==len(ids),'部分复测事件不存在')
    require(all(e.complaint_id==caseid and e.position==sus.position for e in events),'复测事件须为本卷该测点采样')
    links={x.event_id:x for x in db.scalars(select(SuspensionEvent).where(
        SuspensionEvent.suspension_id==sus.id,SuspensionEvent.event_id.in_(ids)))}
    require(set(ids)==set(links),'复测只能选用停用期间登记、等待复测的采样')
    require(all(x.state=='pending' for x in links.values()),
            '不能复用停用时段内已确认隔离的采样；请选恢复后的新采样复测')
    errors=_errors(db,events)
    values=[errors[e.id] for e in events]
    median,mad,cutoff=_cutoff(values)
    # 达标：新采样内部稳定（无一条超自身切点），且整体水平回到原基线切点以内。
    passed=all(v<=cutoff for v in values) and median<=sus.cutoff
    row=Requalification(suspension_id=sus.id,event_ids=ids,baseline_median=median,baseline_mad=mad,
                        cutoff=cutoff,passed=passed,note=data.note);db.add(row);db.flush()
    if not passed:
        for eid in ids:
            links[eid].state='quarantined';links[eid].reconstruction_error=errors[eid]
        record(db,user,'requalification.fail',row.id,f'suspension={sus.id}');db.commit();return dump(row)
    for eid in ids:
        links[eid].state='released';links[eid].reconstruction_error=errors[eid]
    sus.state='released';sus.released_at=now(db);sus.release_note=data.note
    # 恢复后若再次持续偏离，可新开停用时段并保留旧链；放行后刷新受影响归因标记。
    refresh_attribution_flags(db,caseid)
    record(db,user,'requalification.pass',row.id,f'suspension={sus.id};released_at={sus.released_at.isoformat()}')
    db.commit();return dump(row)

def refresh_attribution_flags(db,caseid):
    """归因是否受当前在途停用影响：分离快照含该停用拦住的采样即暂停引用。"""
    active={s.id:s for s in _active(db,caseid)}
    if not active:
        for attr in db.scalars(select(Attribution).where(Attribution.complaint_id==caseid)):
            attr.suspended=False;attr.suspension_ids=[]
        return
    link={}
    for link_row in db.scalars(select(SuspensionEvent).where(SuspensionEvent.suspension_id.in_(active))):
        link.setdefault(link_row.event_id,link_row.suspension_id)
    for attr in db.scalars(select(Attribution).where(Attribution.complaint_id==caseid)):
        job=db.get(Separation,attr.separation_id)
        hit=sorted({link[eid] for eid in (job.event_ids if job else []) if eid in link})
        attr.suspended=bool(hit);attr.suspension_ids=hit

def list_payload(db,caseid):
    rows=db.scalars(select(Suspension).where(Suspension.complaint_id==caseid).order_by(Suspension.id.desc())).all()
    out=[]
    for s in rows:
        item=dump(s)
        item['events']=[dump(x) for x in db.scalars(select(SuspensionEvent).where(SuspensionEvent.suspension_id==s.id).order_by(SuspensionEvent.id))]
        item['requalifications']=[dump(x) for x in db.scalars(select(Requalification).where(Requalification.suspension_id==s.id).order_by(Requalification.id))]
        # 历史可追溯：凡分离快照含本停用拦住采样的归因都列出，放行后也保留。
        linked={x.event_id for x in db.scalars(select(SuspensionEvent).where(SuspensionEvent.suspension_id==s.id))}
        item['affected_attribution_ids']=[]
        for attr in db.scalars(select(Attribution).where(Attribution.complaint_id==caseid).order_by(Attribution.id)):
            job=db.get(Separation,attr.separation_id)
            if job and linked.intersection(job.event_ids):
                item['affected_attribution_ids'].append(attr.id)
        out.append(item)
    return out

def mediation_blocked_attribution(db,caseid,attribution_id):
    """起草协议时核对归因是否落在停用时段内。"""
    active=_active(db,caseid)
    if not active:return
    attr=db.get(Attribution,attribution_id)
    if attr is None:return
    if attr.suspended or attr.suspension_ids:
        require(False,'该归因引用了停用时段采样，已暂停用于调解；复测放行并重新分离归因后再起草协议')
    blocked=quarantined_ids(db,caseid)
    job=db.get(Separation,attr.separation_id)
    if job and any(eid in blocked for eid in job.event_ids):
        require(False,'该归因的分离快照含停用时段采样，已暂停用于调解')
