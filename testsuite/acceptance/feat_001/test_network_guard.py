"""feat-001 (NFR-009): the default test suite cannot reach the network; loopback still works."""

import socket

import pytest

from testsuite.conftest import NetworkAccessBlockedError


def test_outbound_connection_is_blocked() -> None:
    with pytest.raises(NetworkAccessBlockedError):
        socket.create_connection(("203.0.113.10", 443), timeout=1)


def test_dns_lookup_of_external_host_is_blocked() -> None:
    with pytest.raises(NetworkAccessBlockedError):
        socket.getaddrinfo("api.example.com", 443)


def test_loopback_is_allowed() -> None:
    left, right = socket.socketpair()
    with left, right:
        left.sendall(b"ping")
        assert right.recv(4) == b"ping"
