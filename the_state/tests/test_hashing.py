import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from core.hashing import hash_payload


def test_deterministic():
    a = hash_payload({"z": 1, "a": 2})
    b = hash_payload({"a": 2, "z": 1})
    assert a == b


def test_returns_hex_string():
    h = hash_payload({"key": "value"})
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_different_payloads_differ():
    assert hash_payload({"x": 1}) != hash_payload({"x": 2})


def test_empty_payload():
    h = hash_payload({})
    assert len(h) == 64


def test_nested_payload():
    a = hash_payload({"a": {"b": {"c": 3}}})
    b = hash_payload({"a": {"b": {"c": 3}}})
    assert a == b
