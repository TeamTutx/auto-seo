import app.services.site_verification as site_verification
from app.services.site_verification import verify_dns_txt, verify_file_upload, verify_meta_tag


class _FakeTXTRecord:
    def __init__(self, value: str):
        self.strings = [value.encode()]


def test_verify_dns_txt_finds_matching_record(monkeypatch):
    monkeypatch.setattr(
        "dns.resolver.resolve",
        lambda domain, rtype, lifetime=None: [_FakeTXTRecord("unrelated"), _FakeTXTRecord("signal-verify-abc123")],
    )
    verified, message = verify_dns_txt("example.com", "signal-verify-abc123")
    assert verified is True


def test_verify_dns_txt_no_matching_record(monkeypatch):
    monkeypatch.setattr("dns.resolver.resolve", lambda domain, rtype, lifetime=None: [_FakeTXTRecord("unrelated")])
    verified, message = verify_dns_txt("example.com", "signal-verify-abc123")
    assert verified is False


def test_verify_dns_txt_handles_resolution_errors(monkeypatch):
    def _raise(*args, **kwargs):
        raise Exception("NXDOMAIN")

    monkeypatch.setattr("dns.resolver.resolve", _raise)
    verified, message = verify_dns_txt("example.com", "token")
    assert verified is False
    assert "Could not read TXT records" in message


def test_verify_meta_tag_success(monkeypatch):
    monkeypatch.setattr(
        site_verification,
        "fetch_html",
        lambda url: '<html><head><meta name="signal-site-verification" content="tok123"></head></html>',
    )
    verified, _ = verify_meta_tag("example.com", "tok123")
    assert verified is True


def test_verify_meta_tag_wrong_token(monkeypatch):
    monkeypatch.setattr(
        site_verification,
        "fetch_html",
        lambda url: '<html><head><meta name="signal-site-verification" content="other"></head></html>',
    )
    verified, _ = verify_meta_tag("example.com", "tok123")
    assert verified is False


def test_verify_meta_tag_handles_fetch_errors(monkeypatch):
    def _raise(url):
        raise Exception("connection refused")

    monkeypatch.setattr(site_verification, "fetch_html", _raise)
    verified, message = verify_meta_tag("example.com", "tok123")
    assert verified is False
    assert "Could not fetch" in message


def test_verify_file_upload_success(monkeypatch):
    monkeypatch.setattr(site_verification, "fetch_html", lambda url: "  tok123  \n")
    verified, _ = verify_file_upload("example.com", "tok123")
    assert verified is True


def test_verify_file_upload_wrong_content(monkeypatch):
    monkeypatch.setattr(site_verification, "fetch_html", lambda url: "not the token")
    verified, _ = verify_file_upload("example.com", "tok123")
    assert verified is False
