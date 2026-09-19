"""Find a site's pages without the owner typing them in one at a time.

Two strategies, in order of preference:

1. **The sitemap.** If a site publishes one it is the owner's own list of what
   matters, already canonical and free of junk. robots.txt is checked first
   because that is where sitemaps are declared; /sitemap.xml is tried as a
   fallback since plenty of sites have one without advertising it.
2. **Following links.** Only when a sitemap yields too little. A breadth-first
   walk from the home page, same registrable domain only, shallow by default -
   deep crawling other people's servers is not something to do casually.

robots.txt Disallow rules are honoured in both cases. Signal identifies itself
(SignalSEOBot) and a site that asks it not to read a path is obeyed, sitemap or
not - a tool that tells people to fix their SEO cannot ignore the one file that
exists to say "don't".
"""
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

from app.services.fetcher import USER_AGENT

logger = logging.getLogger("signal.crawler")

TIMEOUT = httpx.Timeout(10.0, read=20.0)

# Files that are not pages anyone audits for SEO.
SKIP_EXTENSIONS = {
    ".pdf", ".zip", ".gz", ".tar", ".rar", ".dmg", ".exe", ".apk",
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico", ".bmp",
    ".mp3", ".mp4", ".webm", ".mov", ".avi", ".wav",
    ".css", ".js", ".json", ".xml", ".rss", ".atom", ".txt",
    ".woff", ".woff2", ".ttf", ".eot",
}
# Paths that are never the content a site wants to rank.
SKIP_PATH_HINTS = ("/wp-admin", "/wp-json", "/cgi-bin", "/cart", "/checkout", "/admin")
# Campaign and click-tracking parameters never identify a different page, so
# they are dropped before anything is compared or stored.
TRACKING_PARAMS = ("utm_", "gclid", "fbclid", "msclkid", "mc_cid", "mc_eid", "_ga", "ref_src")


@dataclass
class Discovered:
    url: str
    via: str  # "sitemap" | "link"


def normalise_url(url: str) -> Optional[str]:
    """Canonical form for comparison: no fragment, no trailing slash on a path,
    lowercase host. Returns None for anything that isn't an http(s) page."""
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if any(path.lower().endswith(ext) for ext in SKIP_EXTENSIONS):
        return None
    if any(hint in path.lower() for hint in SKIP_PATH_HINTS):
        return None
    query = urlencode([
        (key, value) for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not any(key.lower().startswith(prefix) for prefix in TRACKING_PARAMS)
    ])
    return urlunparse((parsed.scheme, parsed.netloc.lower(), path, "", query, ""))


def path_key(url: str) -> str:
    """Identity for "is this the same page?". Two URLs differing only by query
    string are nearly always one page rendered differently - /login and
    /login?mode=register are the same template, and auditing both twice wastes
    the owner's page budget on a duplicate. Sitemap entries are exempt: if the
    owner listed both, they meant both."""
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"


def same_site(url: str, domain: str) -> bool:
    """Same registrable domain, ignoring www and subdomain differences like
    blog.example.com - those are still the owner's pages."""
    host = urlparse(url).netloc.lower().removeprefix("www.")
    root = domain.lower().removeprefix("www.")
    return host == root or host.endswith(f".{root}")


def _get(client: httpx.Client, url: str) -> Optional[httpx.Response]:
    try:
        response = client.get(url)
    except httpx.HTTPError as exc:
        logger.info("crawl: %s failed (%s)", url, exc)
        return None
    return response if response.status_code < 400 else None


def load_robots(client: httpx.Client, base: str) -> Tuple[Optional[RobotFileParser], List[str]]:
    """Returns (parser, sitemap URLs declared in robots.txt). A missing or
    unreadable robots.txt means no rules, not "block everything" - that is what
    the standard says and what every other crawler does."""
    response = _get(client, urljoin(base, "/robots.txt"))
    if response is None:
        return None, []
    parser = RobotFileParser()
    try:
        parser.parse(response.text.splitlines())
    except Exception:
        return None, []
    sitemaps = [line.split(":", 1)[1].strip() for line in response.text.splitlines()
                if line.lower().startswith("sitemap:")]
    return parser, sitemaps


def _allowed(robots: Optional[RobotFileParser], url: str) -> bool:
    if robots is None:
        return True
    try:
        return robots.can_fetch(USER_AGENT, url)
    except Exception:
        return True


def parse_sitemap(text: str) -> Tuple[List[str], List[str]]:
    """Returns (page URLs, nested sitemap URLs). A <sitemapindex> points at more
    sitemaps; a <urlset> lists pages. Parsed with a regex over <loc> rather than
    an XML parser because real sitemaps are routinely malformed, and a strict
    parse that throws gets us nothing at all."""
    locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text, flags=re.IGNORECASE)
    if re.search(r"<sitemapindex", text, flags=re.IGNORECASE):
        return [], locs
    return locs, []


def from_sitemaps(client: httpx.Client, base: str, domain: str, candidates: Iterable[str],
                  limit: int, robots: Optional[RobotFileParser]) -> List[str]:
    """Walk sitemaps (following one level of sitemap index) and return page URLs."""
    seen_sitemaps: Set[str] = set()
    queue = list(candidates) + [urljoin(base, "/sitemap.xml"), urljoin(base, "/sitemap_index.xml")]
    found: List[str] = []
    seen: Set[str] = set()

    while queue and len(found) < limit:
        sitemap_url = queue.pop(0)
        if sitemap_url in seen_sitemaps or len(seen_sitemaps) >= 10:
            continue
        seen_sitemaps.add(sitemap_url)

        response = _get(client, sitemap_url)
        if response is None or "<loc" not in response.text.lower():
            continue
        pages, nested = parse_sitemap(response.text)
        queue.extend(nested)
        for raw in pages:
            url = normalise_url(raw)
            if url and url not in seen and same_site(url, domain) and _allowed(robots, url):
                seen.add(url)
                found.append(url)
                if len(found) >= limit:
                    break
    return found


def from_links(client: httpx.Client, base: str, domain: str, limit: int,
               robots: Optional[RobotFileParser], max_depth: int = 2) -> List[str]:
    """Breadth-first from the home page. Shallow on purpose: two levels reaches
    everything a small site links from its navigation, without hammering a
    server we don't own."""
    start = normalise_url(base)
    if start is None:
        return []
    seen: Set[str] = {start}
    seen_paths: Set[str] = {path_key(start)}
    found: List[str] = [start]
    queue: List[Tuple[str, int]] = [(start, 0)]

    while queue and len(found) < limit:
        url, depth = queue.pop(0)
        if depth >= max_depth:
            continue
        response = _get(client, url)
        if response is None or "html" not in response.headers.get("content-type", ""):
            continue
        try:
            soup = BeautifulSoup(response.text, "lxml")
        except Exception:
            continue
        for anchor in soup.find_all("a", href=True):
            link = normalise_url(urljoin(url, anchor["href"]))
            if link is None or link in seen or not same_site(link, domain) or not _allowed(robots, link):
                continue
            if path_key(link) in seen_paths:
                seen.add(link)  # a query-string variant of a page already queued
                continue
            seen.add(link)
            seen_paths.add(path_key(link))
            found.append(link)
            queue.append((link, depth + 1))
            if len(found) >= limit:
                break
    return found


def discover(domain: str, limit: int, scheme: str = "https") -> List[Discovered]:
    """Every page Signal can find for `domain`, capped at `limit`. The home page
    is always first so a site with nothing else still gets something."""
    base = f"{scheme}://{domain.rstrip('/')}"
    headers = {"User-Agent": USER_AGENT}

    with httpx.Client(follow_redirects=True, timeout=TIMEOUT, headers=headers) as client:
        robots, declared = load_robots(client, base)
        sitemap_urls = from_sitemaps(client, base, domain, declared, limit, robots)

        results: List[Discovered] = [Discovered(url, "sitemap") for url in sitemap_urls]
        # A sitemap with one or two entries usually means a stub, not a one-page
        # site, so fall back to following links and merge the two.
        if len(results) < min(limit, 5):
            known_paths = {path_key(d.url) for d in results}
            for url in from_links(client, base, domain, limit, robots):
                if path_key(url) not in known_paths:
                    results.append(Discovered(url, "link"))
                    known_paths.add(path_key(url))

    home = normalise_url(base)
    results.sort(key=lambda d: (d.url != home, d.url))
    return results[:limit]
