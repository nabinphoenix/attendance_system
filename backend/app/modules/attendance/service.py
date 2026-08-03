import math, secrets
from datetime import UTC, datetime, timedelta
from jose import JWTError, jwt
from app.core.config import settings
def generate_qr_token(session_id:int)->tuple[str,datetime]:
    now=datetime.now(UTC); exp=now+timedelta(seconds=settings.qr_token_expire_seconds)
    token=jwt.encode({"session_id":session_id,"nonce":secrets.token_urlsafe(12),"iat":now,"exp":exp,"type":"attendance_qr"},settings.jwt_secret_key,algorithm=settings.jwt_algorithm)
    return token,exp
def validate_qr_token(token:str)->int:
    try: payload=jwt.decode(token,settings.jwt_secret_key,algorithms=[settings.jwt_algorithm])
    except JWTError as exc: raise ValueError("QR token is invalid or expired") from exc
    if payload.get("type")!="attendance_qr": raise ValueError("Invalid QR token type")
    return int(payload["session_id"])
def distance_meters(lat1:float,lon1:float,lat2:float,lon2:float)->float:
    radius=6371000; p1,p2=math.radians(lat1),math.radians(lat2); dp=math.radians(lat2-lat1); dl=math.radians(lon2-lon1)
    a=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2
    return radius*2*math.atan2(math.sqrt(a),math.sqrt(1-a))
