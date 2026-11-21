"""NMF只分解合成频带能量，不识别人、不提供分贝/声源物证结论。"""
import hashlib,json
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.decomposition import NMF
SEED=1040
# 楼道换表后分离仍会给出看似可信的占比，因此另报逐事件重构误差，
# 由各测点正常采样建立基线，持续偏离即停用该时段采样（见suspension_service）。
TRAIN_ROWS=280
HELDOUT_ROWS=80

def _training():
    """固定合成训练链路：fit只触达前280行，返回同一套模型供分离与诊断复用。"""
    rng=np.random.default_rng(SEED)
    templates=np.array([[9,7,2,0.3,0.1,0.1,0.05,0.02],[0.2,0.5,1.5,3,4,3,1,0.3],[0.05,0.2,0.7,3,6,8,5,1]],dtype=float)
    templates/=templates.sum(axis=1,keepdims=True)
    weights=rng.gamma(.7,20,size=(360,3));weights[:30]=np.eye(3)[np.arange(30)%3]*40+0.001
    x=weights@templates+rng.uniform(0,.015,size=(360,8))
    # 原始样本先划分，fit仅触达前280行；后80行是固定留出集。
    train=x[:TRAIN_ROWS];test=x[TRAIN_ROWS:];truth=weights[TRAIN_ROWS:]
    model=NMF(n_components=3,init='nndsvda',random_state=SEED,max_iter=2500,tol=1e-5)
    w=model.fit_transform(train);h=model.components_
    normal=h/h.sum(axis=1,keepdims=True)
    cosine=normal@templates.T/(np.linalg.norm(normal,axis=1)[:,None]*np.linalg.norm(templates,axis=1)[None,:])
    a,b=linear_sum_assignment(-cosine);order=[int(a[list(b).index(i)]) for i in range(3)]
    reconstruction=model.transform(test)@h
    wt=model.transform(test);pred=wt*h.sum(axis=1)[None,:];pred=pred[:,order]
    pred/=pred.sum(axis=1,keepdims=True);truth/=truth.sum(axis=1,keepdims=True)
    return {'model':model,'h':h,'order':order,'normal':normal,
            'heldout_relative_rmse':float(np.linalg.norm(test-reconstruction)/np.linalg.norm(test)),
            'heldout_mixture_mae':float(np.mean(np.abs(pred-truth))),
            'train_reconstruction':float(model.reconstruction_err_),'iterations':int(model.n_iter_),
            'training_checksum':hashlib.sha256(x.tobytes()).hexdigest()}

def _event_rows(model,h,order,events):
    raw=np.array([e['energies'] for e in events],dtype=float)
    wt=model.transform(raw)
    recon=wt@h
    norm=np.linalg.norm(raw,axis=1)
    errors=np.linalg.norm(raw-recon,axis=1)/np.where(norm==0,1.0,norm)
    scaled=wt*h.sum(axis=1)[None,:];scaled=scaled[:,order];scaled/=scaled.sum(axis=1,keepdims=True)
    labels=['equipment','impact','speech']
    return labels,[{'event_id':e['id'],'weights':dict(zip(labels,[float(v) for v in o])),
                    'dominant':labels[int(np.argmax(o))],'reconstruction_error':float(r)}
                   for e,o,r in zip(events,scaled,errors)]

def diagnose(events):
    """逐事件相对重构RMSE，供各测点正常采样基线检测；不产出占比结论。"""
    t=_training();labels,rows=_event_rows(t['model'],t['h'],t['order'],events)
    return {'seed':SEED,'bands':['63Hz','125Hz','250Hz','500Hz','1kHz','2kHz','4kHz','8kHz'],
            'input_checksum':hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest(),
            'sources':labels,'events':rows,
            'limitation':'相对重构误差仅用于识别换表/漂移，不能证明声源或住户身份；停用期间采样不得进入分离与归因。'}

def calculate(events):
    t=_training();labels,rows=_event_rows(t['model'],t['h'],t['order'],events)
    return {'seed':SEED,'input_checksum':hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest(),
            'training_checksum':t['training_checksum'],'training_rows':TRAIN_ROWS,'heldout_rows':HELDOUT_ROWS,
            'heldout_relative_rmse':t['heldout_relative_rmse'],'heldout_mixture_mae':t['heldout_mixture_mae'],
            'train_reconstruction':t['train_reconstruction'],'iterations':t['iterations'],
            'bands':['63Hz','125Hz','250Hz','500Hz','1kHz','2kHz','4kHz','8kHz'],
            'templates':t['normal'][t['order']].tolist(),'sources':labels,'events':rows,
            'limitation':'固定合成样本仅验证分解链路；频带能量不能证明真实声源或身份，须人工现场证据复核。'}
