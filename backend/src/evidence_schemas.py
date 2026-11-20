from datetime import datetime
from pydantic import BaseModel,Field,field_validator
import math
from typing import Literal
class EventInput(BaseModel):
    measured_at:datetime
    position:str=Field(min_length=2,max_length=60)
    duration_s:int=Field(ge=1,le=3600)
    energies:list[float]=Field(min_length=8,max_length=8)
    note:str=Field(default='合成频带，无原始录音',min_length=6,max_length=300)
    @field_validator('energies')
    @classmethod
    def finite(cls,v):
        if not all(math.isfinite(x) and 0<=x<=1000 for x in v) or sum(v)<=0:raise ValueError('8个频带须非负、有限且总能量大于0')
        return v
    @field_validator('measured_at')
    @classmethod
    def naive(cls,v):
        if v.tzinfo:raise ValueError('使用本地无时区时间')
        return v
class AttributionInput(BaseModel):
    separation_id:int=Field(gt=0)
    source:Literal['equipment','impact','speech','undetermined']
    evidence:str=Field(min_length=10,max_length=500)
