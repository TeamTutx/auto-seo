"""Domain ownership verification (REQUIREMENTS.md §2.1): DNS TXT, meta tag,
or a hosted file - same three options Google Search Console offers. Each
verifier returns (verified, message) instead of raising, since "not verified
yet" is an expected, normal outcome (e.g. DNS hasn't propagated), not an error.
"""
from typing import Tuple

import dns.resolver
from bs4 import BeautifulSoup

from app.services.fetcher import fetch_html

DNS_TIMEOUT = 5.0
META_TAG_NAME = "signal-site-verification"
VERIFICATION_FILENAME = "signal-verification.txt"


def verify_dns_txt(domain: str, token: str) -> Tuple[bool, str]:
    try:
        answers = dns.resolver.resolve(domain, "TXT", lifetime=DNS_TIMEOUT)
    except Exception as exc:
        return False, f"Could not read TXT records for {domain}: {exc}"

    for rdata in answers:
        value = b"".join(rdata.strings).decode("utf-8", errors="ignore")
        if token in value:
            return True, "Found a matching TXT record."

    return False, (
        f"No TXT record containing the verification token was found at {domain}. "
        "DNS changes can take a while to propagate - try again shortly if you just added it."
    )


def verify_meta_tag(domain: str, token: str) -> Tuple[bool, str]:
    url = f"https://{domain}/"
    try:
        html = fetch_html(url)
    except Exception as exc:
        return False, f"Could not fetch {url}: {exc}"

    soup = BeautifulSoup(html, "lxml")
    tag = soup.find("meta", attrs={"name": META_TAG_NAME})
    if tag and tag.get("content", "").strip() == token:
        return True, "Found a matching meta tag."

    return False, f'No <meta name="{META_TAG_NAME}" content="..."> matching the verification token was found on {url}.'


def verify_file_upload(domain: str, token: str) -> Tuple[bool, str]:
    url = f"https://{domain}/{VERIFICATION_FILENAME}"
    try:
        content = fetch_html(url)
    except Exception as exc:
        return False, f"Could not fetch {url}: {exc}"

    if content.strip() == token:
        return True, "File content matches the verification token."

    return False, f"{url} doesn't contain exactly the verification token."
