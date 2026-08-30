import base64
import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from jose.exceptions import ExpiredSignatureError
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.core.config import settings
from .models import AttendanceChallenge
from app.modules.scheduling.models import ClassSession


class QRValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QRClaims:
    session_id: int
    version: int
    nonce: str
    issued_at: datetime
    expires_at: datetime


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _encode_qr(session_id: int, version: int, nonce: str, issued_at: datetime, expires_at: datetime) -> str:
    return jwt.encode(
        {
            "session_id": session_id,
            "qr_version": version,
            "nonce": nonce,
            "iat": int(utc(issued_at).timestamp()),
            "exp": int(utc(expires_at).timestamp()),
            "type": "attendance_qr",
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def issue_qr_token(session: ClassSession, now: datetime | None = None, *, force: bool = False) -> tuple[str, datetime, bool]:
    """Return the current rotation, issuing a new generation only after expiry."""

    now = utc(now or datetime.now(UTC))
    expires = utc(session.qr_expires_at) if session.qr_expires_at else None
    issued = utc(session.qr_issued_at) if session.qr_issued_at else None
    if force or not session.qr_nonce or not issued or not expires or expires <= now:
        session.qr_version = (session.qr_version or 0) + 1
        session.qr_nonce = secrets.token_urlsafe(24)
        session.qr_issued_at = now
        session.qr_expires_at = now + timedelta(seconds=session.challenge_rotation_seconds or settings.attendance_challenge_rotation_seconds)
        # Transitional column retained by the schema; raw QR secrets are no longer persisted.
        session.current_qr_token = None
        issued = now
        expires = utc(session.qr_expires_at)
        created = True
    else:
        created = False
    return _encode_qr(session.id, session.qr_version, session.qr_nonce, issued, expires), expires, created


def _challenge_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode()).digest())
    return Fernet(key)


def _code_hash(code: str) -> str:
    return hmac.new(settings.jwt_secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def generate_classroom_code() -> str:
    length = settings.attendance_code_length
    if length < 1 or length > 10:
        raise ValueError("attendance_code_length must be between 1 and 10")
    return str(secrets.randbelow(10 ** length)).zfill(length)


def reveal_classroom_code(challenge: AttendanceChallenge) -> str:
    try:
        return _challenge_cipher().decrypt(challenge.code_ciphertext.encode()).decode()
    except (InvalidToken, UnicodeDecodeError) as exc:
        raise RuntimeError("Attendance challenge code could not be decrypted") from exc


def classroom_code_matches(challenge: AttendanceChallenge, code: str) -> bool:
    return hmac.compare_digest(challenge.code_hash, _code_hash(code))


def verification_token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_qr_challenge(db, session: ClassSession, created_by: int, now: datetime | None = None, *, force: bool = False) -> tuple[str, datetime, AttendanceChallenge, str, bool]:
    """Issue or return the active QR/challenge pair. Only callers authorized as teachers receive the code."""

    now = utc(now or datetime.now(UTC))
    token, expires, qr_created = issue_qr_token(session, now, force=force)
    challenge = db.scalar(
        select(AttendanceChallenge).where(
            AttendanceChallenge.class_session_id == session.id,
            AttendanceChallenge.qr_version == session.qr_version,
        )
    )
    created = qr_created or challenge is None
    if created:
        for previous in db.scalars(
            select(AttendanceChallenge).where(
                AttendanceChallenge.class_session_id == session.id,
                AttendanceChallenge.revoked_at.is_(None),
            )
        ).all():
            previous.revoked_at = now
        code = generate_classroom_code()
        challenge = AttendanceChallenge(
            class_session_id=session.id,
            qr_version=session.qr_version,
            qr_nonce=session.qr_nonce,
            code_hash=_code_hash(code),
            code_ciphertext=_challenge_cipher().encrypt(code.encode()).decode(),
            created_by=created_by,
            created_at=now,
            expires_at=expires,
        )
        db.add(challenge)
        db.flush()
    else:
        code = reveal_classroom_code(challenge)
    return token, expires, challenge, code, created


def challenge_is_current(session: ClassSession, challenge: AttendanceChallenge, now: datetime | None = None) -> bool:
    now = utc(now or datetime.now(UTC))
    return bool(
        challenge.revoked_at is None
        and utc(challenge.expires_at) > now
        and session.qr_version == challenge.qr_version
        and session.qr_nonce == challenge.qr_nonce
    )


def validate_qr_token(token: str) -> QRClaims:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except ExpiredSignatureError as exc:
        raise QRValidationError("QR_EXPIRED", "This QR code has expired") from exc
    except JWTError as exc:
        raise QRValidationError("INVALID_QR", "This QR code is invalid") from exc
    try:
        if payload.get("type") != "attendance_qr":
            raise ValueError
        return QRClaims(
            session_id=int(payload["session_id"]),
            version=int(payload["qr_version"]),
            nonce=str(payload["nonce"]),
            issued_at=datetime.fromtimestamp(int(payload["iat"]), UTC),
            expires_at=datetime.fromtimestamp(int(payload["exp"]), UTC),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise QRValidationError("INVALID_QR", "This QR code is invalid") from exc


def distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
