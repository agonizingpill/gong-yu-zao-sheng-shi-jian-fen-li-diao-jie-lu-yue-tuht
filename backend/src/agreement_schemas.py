from pydantic import BaseModel,Field,model_validator
class AgreementInput(BaseModel):
    attribution_id:int=Field(gt=0)
    party_a:str=Field(min_length=2,max_length=40)
    party_b:str=Field(min_length=2,max_length=40)
    quiet_from:int=Field(ge=0,le=1439)
    quiet_to:int=Field(ge=0,le=1439)
    threshold:float=Field(gt=0,le=5000,allow_inf_nan=False)
    observation_days:int=Field(ge=1,le=30)
    @model_validator(mode='after')
    def distinct(self):
        if self.party_a.strip()==self.party_b.strip():raise ValueError('必须两名不同参与方')
        if self.quiet_from==self.quiet_to:raise ValueError('起止时刻不可相同')
        self.party_a=self.party_a.strip();self.party_b=self.party_b.strip()
        return self
class SignatureInput(BaseModel):
    party:str=Field(min_length=2,max_length=40)
    proof:str=Field(min_length=8,max_length=300)
class RemedyInput(BaseModel):
    instruction:str=Field(min_length=8,max_length=400)
    responsible:str=Field(min_length=2,max_length=40)
class ReceiptInput(BaseModel):
    receipt:str=Field(min_length=8,max_length=300)
class RecheckInput(BaseModel):
    event_id:int=Field(gt=0)
    note:str=Field(min_length=6,max_length=300)
class ResolutionInput(BaseModel):
    resolution:str=Field(min_length=10,max_length=300)
