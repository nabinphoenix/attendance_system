from datetime import datetime
from pydantic import BaseModel
class CheckInRequest(BaseModel): qr_token:str; latitude:float; longitude:float; accuracy:float
class CheckInResponse(BaseModel): attendance_id:int; status:str; check_in_time:datetime
class QRResponse(BaseModel): token:str; expires_at:datetime; expires_in_seconds:int
class RosterItem(BaseModel): attendance_id:int|None; student_id:int; student_name:str; roll_number:str; status:str
class StatusChange(BaseModel): status:str; reason:str
