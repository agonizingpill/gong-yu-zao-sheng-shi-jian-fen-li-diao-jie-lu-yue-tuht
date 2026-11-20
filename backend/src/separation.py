"""NMF只分解合成频带能量，不识别人、不提供分贝/声源物证结论。"""
import hashlib,json
import numpy as np
from scipy.optimize import linear_sum_assignment
from sklearn.decomposition import NMF
SEED=1040

def calculate(events):
    rng=np.random.default_rng(SEED)
    templates=np.array([[9,7,2,0.3,0.1,0.1,0.05,0.02],[0.2,0.5,1.5,3,4,3,1,0.3],[0.05,0.2,0.7,3,6,8,5,1]],dtype=float)
    templates/=templates.sum(axis=1,keepdims=True)
    weights=rng.gamma(.7,20,size=(360,3));weights[:30]=np.eye(3)[np.arange(30)%3]*40+0.001
    x=weights@templates+rng.uniform(0,.015,size=(360,8))
    # 原始样本先划分，fit仅触达前280行；后80行是固定留出集。
    train=x[:280];test=x[280:];truth=weights[280:]
    model=NMF(n_components=3,init='nndsvda',random_state=SEED,max_iter=2500,tol=1e-5)
    w=model.fit_transform(train);h=model.components_
    normal=h/h.sum(axis=1,keepdims=True)
    cosine=normal@templates.T/(np.linalg.norm(normal,axis=1)[:,None]*np.linalg.norm(templates,axis=1)[None,:])
    a,b=linear_sum_assignment(-cosine);order=[int(a[list(b).index(i)]) for i in range(3)]
    wt=model.transform(test);pred=wt*h.sum(axis=1)[None,:];pred=pred[:,order]
    pred/=pred.sum(axis=1,keepdims=True);truth/=truth.sum(axis=1,keepdims=True)
    reconstruction=wt@h
    raw=np.array([e['energies'] for e in events]);out=model.transform(raw)*h.sum(axis=1)[None,:];out=out[:,order];out/=out.sum(axis=1,keepdims=True)
    labels=['equipment','impact','speech']
    return {'seed':SEED,'input_checksum':hashlib.sha256(json.dumps(events,sort_keys=True).encode()).hexdigest(),'training_checksum':hashlib.sha256(x.tobytes()).hexdigest(),'training_rows':280,'heldout_rows':80,'heldout_relative_rmse':float(np.linalg.norm(test-reconstruction)/np.linalg.norm(test)),'heldout_mixture_mae':float(np.mean(np.abs(pred-truth))),'train_reconstruction':float(model.reconstruction_err_),'iterations':int(model.n_iter_),'bands':['63Hz','125Hz','250Hz','500Hz','1kHz','2kHz','4kHz','8kHz'],'templates':normal[order].tolist(),'sources':labels,'events':[{'event_id':e['id'],'weights':dict(zip(labels,[float(v) for v in o])),'dominant':labels[int(np.argmax(o))]} for e,o in zip(events,out)],'limitation':'固定合成样本仅验证分解链路；频带能量不能证明真实声源或身份，须人工现场证据复核。'}
