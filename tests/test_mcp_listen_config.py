"""Tests for MCP bind defaults and transport-security env parsing."""

import os

from src.mcp_listen_config import (
    build_transport_security_settings,
    cors_extra_origins,
    default_listen_host,
    env_truthy,
    split_csv_env,
)


def test_env_truthy():
    assert env_truthy("UNITARES_TEST_X", default=False) is False
    os.environ["UNITARES_TEST_X"] = "1"
    assert env_truthy("UNITARES_TEST_X") is True
    os.environ["UNITARES_TEST_X"] = "no"
    assert env_truthy("UNITARES_TEST_X") is False
    del os.environ["UNITARES_TEST_X"]


def test_split_csv_env():
    os.environ["UNITARES_TEST_CSV"] = " a , b , "
    assert split_csv_env("UNITARES_TEST_CSV") == ["a", "b"]
    del os.environ["UNITARES_TEST_CSV"]


def test_default_listen_host_loopback(monkeypatch):
    monkeypatch.delenv("UNITARES_MCP_HOST", raising=False)
    monkeypatch.delenv("UNITARES_BIND_ALL_INTERFACES", raising=False)
    assert default_listen_host() == "127.0.0.1"


def test_default_listen_host_bind_all(monkeypatch):
    monkeypatch.delenv("UNITARES_MCP_HOST", raising=False)
    monkeypatch.setenv("UNITARES_BIND_ALL_INTERFACES", "1")
    assert default_listen_host() == "0.0.0.0"


def test_default_listen_host_explicit(monkeypatch):
    monkeypatch.setenv("UNITARES_MCP_HOST", "10.0.0.5")
    assert default_listen_host() == "10.0.0.5"


def test_build_transport_security_merges_extras(monkeypatch):
    monkeypatch.delenv("UNITARES_MCP_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("UNITARES_MCP_ALLOWED_ORIGINS", raising=False)
    monkeypatch.setenv("UNITARES_MCP_ALLOW_NULL_ORIGIN", "0")
    ts = build_transport_security_settings()
    assert "127.0.0.1:*" in ts.allowed_hosts
    assert "null" not in ts.allowed_origins

    monkeypatch.setenv("UNITARES_MCP_ALLOWED_HOSTS", "example.test:*")
    monkeypatch.setenv("UNITARES_MCP_ALLOWED_ORIGINS", "https://example.test:*")
    monkeypatch.setenv("UNITARES_MCP_ALLOW_NULL_ORIGIN", "1")
    ts2 = build_transport_security_settings()
    assert "example.test:*" in ts2.allowed_hosts
    assert "https://example.test:*" in ts2.allowed_origins
    assert "null" in ts2.allowed_origins


def test_cors_extra_origins(monkeypatch):
    monkeypatch.setenv("UNITARES_HTTP_CORS_EXTRA_ORIGINS", "http://a:1,http://b:2")
    assert cors_extra_origins() == ["http://a:1", "http://b:2"]
    monkeypatch.delenv("UNITARES_HTTP_CORS_EXTRA_ORIGINS", raising=False)
    assert cors_extra_origins() == []
