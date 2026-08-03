from pydantic import BaseModel
class CheckInRequest(BaseModel):
    qr_token: str
    latitude: float
    longitude: float
