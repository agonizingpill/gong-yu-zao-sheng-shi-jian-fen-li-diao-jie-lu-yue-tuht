from pydantic import BaseModel,Field,field_validator
from datetime import datetime
class Login(BaseModel):
    username:str=Field(min_length=1,max_length=60)
    password:str=Field(min_length=1,max_length=100)
class ComplaintInput(BaseModel):
    code:str=Field(pattern=r'^[A-Z0-9-]{3,40}$')
    alias:str=Field(min_length=2,max_length=40)
    building:str=Field(min_length=1,max_length=40)
    summary:str=Field(min_length=8,max_length=400)
    consent:bool=False
    @field_validator('alias','building','summary')
    @classmethod
    def stripped(cls,v):
        if not v.strip(): raise ValueError('不可全为空格')
        return v.strip()
class ConsentInput(BaseModel):
    granted:bool
    note:str=Field(min_length=6,max_length=300)
class ClockInput(BaseModel):
    at:datetime
    @field_validator('at')
    @classmethod
    def naive(cls,v):
        if v.tzinfo:raise ValueError('演示时钟使用本地无时区时间')
        return v
class NoteInput(BaseModel):
    note:str=Field(min_length=6,max_length=400)
