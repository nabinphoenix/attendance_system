from collections.abc import Iterable
from ipaddress import ip_address, ip_network

from fastapi import Request
from sqlalchemy import select

from app.core.config import settings
from app.modules.platform.models import College

from .models import CampusNetwork


def get_client_ip(request: Request) -> str | None:
    if request.client is None or not request.client.host:
        return None
    hops: list[str] = []
    forwarded_values = request.headers.getlist("x-forwarded-for")
    if len(forwarded_values) > 1:
        return None
    forwarded_for = forwarded_values[0] if forwarded_values else None
    if forwarded_for is not None:
        hops.extend(value.strip() for value in forwarded_for.split(","))
    hops.append(request.client.host)

    try:
        addresses = [ip_address(value) for value in hops]
        trusted_networks = [ip_network(cidr, strict=False) for cidr in settings.trusted_proxy_cidrs]
    except ValueError:
        return None

    for address in reversed(addresses):
        if not any(address in network for network in trusted_networks):
            return str(address)
    return None


def active_campus_cidrs(db, college_id: int | None) -> list[str]:
    if college_id is None:
        return []
    return list(
        db.scalars(
            select(CampusNetwork.cidr).where(
                CampusNetwork.college_id == college_id,
                CampusNetwork.is_active.is_(True),
            )
        ).all()
    )


def classify_ip(
    ip: str | None,
    campus_cidrs: Iterable[str],
    teacher_ip: str | None,
    teacher_status: str | None,
) -> str:
    if ip is None:
        return "unknown"
    try:
        address = ip_address(ip.strip())
    except ValueError:
        return "unknown"
    if address.is_loopback:
        return "unknown"

    try:
        campus_networks = [ip_network(str(cidr), strict=False) for cidr in campus_cidrs]
    except ValueError:
        return "unknown"
    if any(address in network for network in campus_networks):
        return "campus"

    if teacher_status == "campus" and teacher_ip:
        try:
            if address == ip_address(teacher_ip.strip()):
                return "same_as_teacher"
        except ValueError:
            pass
    return "outside"


def college_ip_status(
    db,
    college_id: int | None,
    client_ip: str | None,
    teacher_ip: str | None = None,
    teacher_status: str | None = None,
) -> str:
    college = db.get(College, college_id) if college_id is not None else None
    if not college or college.ip_policy == "off":
        return "unknown"
    return classify_ip(client_ip, active_campus_cidrs(db, college_id), teacher_ip, teacher_status)
