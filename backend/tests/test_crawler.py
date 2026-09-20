"""The crawler's parsing and filtering, with no network involved."""
import httpx
import pytest

from app.services import crawler


class FakeClient:
    """Stands in for httpx.Client, answering from a dict of url -> (status, body)."""

    def __init__(self, pages):
        self.pages = pages
        self.requested = []

    def get(self, url):
        self.requested.append(url)
        if url not in self.pages:
            raise httpx.ConnectError("not found", request=httpx.Request("GET", url))
        status, body, content_type = self.pages[url]
        return httpx.Response(
            status, text=body, headers={"content-type": content_type},
            request=httpx.Request("GET", url),
        )


# --- URL normalisation ---

@pytest.mark.parametrize("raw, expected", [
    ("https://example.com/a#section", "https://example.com/a"),
    ("https://EXAMPLE.com/A", "https://example.com/A"),  # host lowercased, path isn't - paths are case-sensitive
    ("https://example.com", "https://example.com/"),
    ("https://example.com/search?q=1", "https://example.com/search?q=1"),
])
def test_urls_are_tidied_for_storage(raw, expected):
    assert crawler.normalise_url(raw) == expected


@pytest.mark.parametrize("raw", ["https://example.com/about/", "https://example.com/about"])
def test_the_sites_own_trailing_slash_is_preserved(raw):
    """The trailing slash is the site's canonical form, and Search Console
    matches a page by exact URL. Rewriting it would store a URL Google has never
    heard of, and every search query for that page would come back empty."""
    assert crawler.normalise_url(raw) == raw


def test_slash_variants_are_one_page_for_de_duplication():
    """Preserved in what's stored, ignored when deciding if two URLs are the
    same page."""
    assert crawler.path_key("https://example.com/about/") == crawler.path_key("https://example.com/about")


@pytest.mark.parametrize("raw", [
    "mailto:hi@example.com",
    "javascript:void(0)",
    "https://example.com/brochure.pdf",
    "https://example.com/logo.png",
    "https://example.com/app.js",
    "https://example.com/wp-admin/edit.php",
    "/relative/only",
])
def test_non_pages_are_rejected(raw):
    assert crawler.normalise_url(raw) is None


@pytest.mark.parametrize("url, domain, expected", [
    ("https://example.com/a", "example.com", True),
    ("https://www.example.com/a", "example.com", True),
    ("https://blog.example.com/a", "example.com", True),  # subdomains are still the owner's
    ("https://example.com.evil.net/a", "example.com", False),  # the classic suffix trick
    ("https://notexample.com/a", "example.com", False),
])
def test_same_site_matching(url, domain, expected):
    assert crawler.same_site(url, domain) is expected


# --- sitemaps ---

def test_sitemap_index_is_followed_one_level():
    index = """<?xml version="1.0"?><sitemapindex>
      <sitemap><loc>https://example.com/posts.xml</loc></sitemap>
    </sitemapindex>"""
    posts = """<?xml version="1.0"?><urlset>
      <url><loc>https://example.com/a</loc></url>
      <url><loc>https://example.com/b</loc></url>
    </urlset>"""
    client = FakeClient({
        "https://example.com/sitemap.xml": (200, index, "application/xml"),
        "https://example.com/posts.xml": (200, posts, "application/xml"),
    })

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", [], limit=50, robots=None)

    assert found == ["https://example.com/a", "https://example.com/b"]


def test_a_malformed_sitemap_still_yields_its_urls():
    """Real sitemaps are routinely broken; a strict XML parse would return
    nothing where a person can plainly see the URLs."""
    broken = "<urlset><url><loc>https://example.com/a</loc></url><url><loc>https://example.com/b</loc>"
    client = FakeClient({"https://example.com/sitemap.xml": (200, broken, "application/xml")})

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", [], limit=50, robots=None)

    assert found == ["https://example.com/a", "https://example.com/b"]


def test_sitemap_urls_for_other_domains_are_dropped():
    xml = """<urlset>
      <url><loc>https://example.com/a</loc></url>
      <url><loc>https://someone-else.com/b</loc></url>
    </urlset>"""
    client = FakeClient({"https://example.com/sitemap.xml": (200, xml, "application/xml")})

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", [], limit=50, robots=None)

    assert found == ["https://example.com/a"]


def test_the_limit_is_respected():
    urls = "".join(f"<url><loc>https://example.com/p{i}</loc></url>" for i in range(50))
    client = FakeClient({"https://example.com/sitemap.xml": (200, f"<urlset>{urls}</urlset>", "application/xml")})

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", limit=5, candidates=[], robots=None)

    assert len(found) == 5


# --- robots.txt ---

def test_robots_disallow_is_obeyed():
    """A tool that tells people to fix their SEO cannot ignore robots.txt."""
    robots_txt = "User-agent: *\nDisallow: /private\nSitemap: https://example.com/sm.xml\n"
    xml = """<urlset>
      <url><loc>https://example.com/public</loc></url>
      <url><loc>https://example.com/private/secret</loc></url>
    </urlset>"""
    client = FakeClient({
        "https://example.com/robots.txt": (200, robots_txt, "text/plain"),
        "https://example.com/sm.xml": (200, xml, "application/xml"),
    })

    robots, declared = crawler.load_robots(client, "https://example.com")
    found = crawler.from_sitemaps(client, "https://example.com", "example.com", declared, 50, robots)

    assert declared == ["https://example.com/sm.xml"]
    assert found == ["https://example.com/public"]


def test_a_missing_robots_txt_means_no_rules_not_blocked():
    client = FakeClient({})

    robots, declared = crawler.load_robots(client, "https://example.com")

    assert robots is None and declared == []


# --- link following ---

def test_links_are_followed_from_the_home_page():
    home = '<a href="/about">About</a> <a href="https://example.com/pricing">Pricing</a> <a href="https://other.com/x">Off-site</a>'
    client = FakeClient({
        "https://example.com/": (200, home, "text/html"),
        "https://example.com/about": (200, "<p>about</p>", "text/html"),
        "https://example.com/pricing": (200, "<p>pricing</p>", "text/html"),
    })

    found = crawler.from_links(client, "https://example.com", "example.com", limit=50, robots=None)

    assert found == ["https://example.com/", "https://example.com/about", "https://example.com/pricing"]


def test_link_following_does_not_loop_on_circular_links():
    client = FakeClient({
        "https://example.com/": (200, '<a href="/a">a</a>', "text/html"),
        "https://example.com/a": (200, '<a href="/">home</a><a href="/a">self</a>', "text/html"),
    })

    found = crawler.from_links(client, "https://example.com", "example.com", limit=50, robots=None)

    assert found == ["https://example.com/", "https://example.com/a"]


def test_a_sitemaps_trailing_slashes_survive_into_what_is_stored():
    """A WordPress-style site whose canonical URLs end in / must be stored that
    way, or its Search Console data is unreachable."""
    xml = """<urlset>
      <url><loc>https://example.com/about/</loc></url>
      <url><loc>https://example.com/blog/post/</loc></url>
    </urlset>"""
    client = FakeClient({"https://example.com/sitemap.xml": (200, xml, "application/xml")})

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", [], limit=50, robots=None)

    assert found == ["https://example.com/about/", "https://example.com/blog/post/"]


def test_a_sitemap_listing_both_slash_forms_yields_one_page():
    xml = """<urlset>
      <url><loc>https://example.com/about/</loc></url>
      <url><loc>https://example.com/about</loc></url>
    </urlset>"""
    client = FakeClient({"https://example.com/sitemap.xml": (200, xml, "application/xml")})

    found = crawler.from_sitemaps(client, "https://example.com", "example.com", [], limit=50, robots=None)

    assert found == ["https://example.com/about/"]  # first wins, so the sitemap's own order decides


def test_query_string_variants_of_the_same_page_are_not_crawled_twice():
    """A link to /login?mode=register is the same page as /login; auditing both
    would spend two of the owner's fifty page slots on one template."""
    home = '<a href="/login">Sign in</a> <a href="/login?mode=register">Sign up</a>'
    client = FakeClient({
        "https://example.com/": (200, home, "text/html"),
        "https://example.com/login": (200, "<p>login</p>", "text/html"),
    })

    found = crawler.from_links(client, "https://example.com", "example.com", limit=50, robots=None)

    assert found == ["https://example.com/", "https://example.com/login"]


@pytest.mark.parametrize("raw, expected", [
    ("https://example.com/a?utm_source=x&utm_medium=y", "https://example.com/a"),
    ("https://example.com/a?gclid=123", "https://example.com/a"),
    ("https://example.com/a?id=5&utm_campaign=z", "https://example.com/a?id=5"),
])
def test_tracking_parameters_are_stripped(raw, expected):
    """utm_* and click ids never identify a different page."""
    assert crawler.normalise_url(raw) == expected
