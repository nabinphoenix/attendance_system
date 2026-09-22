from starlette.requests import Request

from app.modules.attendance.network import get_client_ip


def request_with_headers(x_forwarded_for: str | None = None, socket_host: str = "127.0.0.1") -> Request:
    headers = [] if x_forwarded_for is None else [(b"x-forwarded-for", x_forwarded_for.encode())]
    scope = {
        "type": "http",
        "headers": headers,
        "client": (socket_host, 8000),
    }
    return Request(scope)


def test_fake_leftmost_forwarded_value_is_ignored() -> None:
    request = request_with_headers("198.51.100.99, 203.0.113.10, 10.0.0.20")

    assert get_client_ip(request) == "203.0.113.10"


def test_normal_forwarded_chain_returns_real_client() -> None:
    request = request_with_headers("198.51.100.10, 10.0.0.20, 172.64.0.10")

    assert get_client_ip(request) == "198.51.100.10"


def test_ipv6_forwarded_chain_returns_real_client() -> None:
    request = request_with_headers("2001:db8::42, 2606:4700::10")

    assert get_client_ip(request) == "2001:db8::42"


def test_malformed_forwarded_header_returns_none() -> None:
    request = request_with_headers("198.51.100.10, not-an-ip, 10.0.0.20")

    assert get_client_ip(request) is None


def test_direct_request_returns_untrusted_socket_peer() -> None:
    request = request_with_headers(socket_host="198.51.100.20")

    assert get_client_ip(request) == "198.51.100.20"