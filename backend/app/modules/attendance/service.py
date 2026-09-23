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
from app.modules.scheduling.models import ClassSession, SessionStatus


class QRValidationError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class QRClaims:
    session_id: int
    version: int
    nonce: str
    issued_at: datetime | None = None
    expires_at: datetime | None = None


# The QR is displayed from a classroom screen, so its encoded text needs to be
# deliberately small. Keeping this alphabet uppercase plus digits and colons
# lets QR encoders use their efficient alphanumeric mode instead of byte mode.
QR_TOKEN_PREFIX = "AQ1"
QR_NONCE_BYTES = 10
QR_SIGNATURE_BYTES = 12


def _is_compact_nonce(value: str | None) -> bool:
    return bool(value and len(value) == 16 and all(character in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in value))


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _base32(value: bytes) -> str:
    return base64.b32encode(value).decode("ascii").rstrip("=")


def _compact_qr_signature(payload: str) -> str:
    digest = hmac.new(settings.jwt_secret_key.encode(), payload.encode("ascii"), hashlib.sha256).digest()
    return _base32(digest[:QR_SIGNATURE_BYTES])


def _encode_compact_qr(session_id: int, version: int, nonce: str) -> str:
    payload = f"{QR_TOKEN_PREFIX}:{session_id}:{version}:{nonce}"
    return f"{payload}:{_compact_qr_signature(payload)}"


def _encode_legacy_qr(session_id: int, version: int, nonce: str, issued_at: datetime, expires_at: datetime) -> str:
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
    if force or not _is_compact_nonce(session.qr_nonce) or not issued or not expires or expires <= now:
        session.qr_version = (session.qr_version or 0) + 1
        session.qr_nonce = _base32(secrets.token_bytes(QR_NONCE_BYTES))
        session.qr_issued_at = now
        session.qr_expires_at = now + timedelta(seconds=session.challenge_rotation_seconds or settings.attendance_challenge_rotation_seconds)
        # Transitional column retained by the schema; raw QR secrets are no longer persisted.
        session.current_qr_token = None
        issued = now
        expires = utc(session.qr_expires_at)
        created = True
    else:
        created = False
    return _encode_compact_qr(session.id, session.qr_version, session.qr_nonce), expires, created


def _challenge_cipher() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.jwt_secret_key.encode()).digest())
    return Fernet(key)


def _code_hash(code: str) -> str:
    return hmac.new(settings.jwt_secret_key.encode(), code.encode(), hashlib.sha256).hexdigest()


def classroom_code_hash(code: str) -> str:
    return _code_hash(code)


def generate_classroom_code() -> str:
    length = settings.attendance_code_length
    if length < 1 or length > 10:
        raise ValueError("attendance_code_length must be between 1 and 10")
    return str(secrets.randbelow(10 ** length)).zfill(length)


def unique_classroom_code(db) -> str:
    for _ in range(20):
        code = generate_classroom_code()
        collision = db.scalar(
            select(AttendanceChallenge.id)
            .join(ClassSession, AttendanceChallenge.class_session_id == ClassSession.id)
            .where(
                AttendanceChallenge.code_hash == _code_hash(code),
                AttendanceChallenge.revoked_at.is_(None),
                ClassSession.status == SessionStatus.ACTIVE,
            )
        )
        if collision is None:
            return code
    raise RuntimeError("Could not issue a unique attendance code")


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
        previous_active = db.scalar(
            select(AttendanceChallenge)
            .where(
                AttendanceChallenge.class_session_id == session.id,
                AttendanceChallenge.revoked_at.is_(None),
            )
            .order_by(AttendanceChallenge.id.desc())
        )
        if previous_active is not None and not force:
            code_hash = previous_active.code_hash
            code_ciphertext = previous_active.code_ciphertext
            code = reveal_classroom_code(previous_active)
        else:
            code = unique_classroom_code(db)
            code_hash = _code_hash(code)
            code_ciphertext = _challenge_cipher().encrypt(code.encode()).decode()
        for previous in db.scalars(
            select(AttendanceChallenge).where(
                AttendanceChallenge.class_session_id == session.id,
                AttendanceChallenge.revoked_at.is_(None),
            )
        ).all():
            previous.revoked_at = now
        challenge = AttendanceChallenge(
            class_session_id=session.id,
            qr_version=session.qr_version,
            qr_nonce=session.qr_nonce,
            code_hash=code_hash,
            code_ciphertext=code_ciphertext,
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


def _validate_compact_qr(token: str) -> QRClaims:
    parts = token.split(":")
    if len(parts) != 5 or parts[0] != QR_TOKEN_PREFIX:
        raise QRValidationError("INVALID_QR", "This QR code is invalid")
    _, session_id, version, nonce, signature = parts
    payload = ":".join(parts[:-1])
    if not hmac.compare_digest(signature, _compact_qr_signature(payload)):
        raise QRValidationError("INVALID_QR", "This QR code is invalid")
    try:
        if len(nonce) != 16 or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567" for character in nonce):
            raise ValueError
        return QRClaims(session_id=int(session_id), version=int(version), nonce=nonce)
    except ValueError as exc:
        raise QRValidationError("INVALID_QR", "This QR code is invalid") from exc


def validate_qr_token(token: str) -> QRClaims:
    if token.startswith(f"{QR_TOKEN_PREFIX}:"):
        return _validate_compact_qr(token)

    # Permit already-issued JWT QR codes to finish an in-progress class after a
    # deployment. New challenges always use the compact token above.
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
