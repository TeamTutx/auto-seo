from app.models import CheckStatus
from app.services.audit_engine import run_onpage_audit

GOOD_HTML = """
<html>
<head>
  <title>Best Running Shoes for Beginners in 2026</title>
  <meta name="description" content="A practical, no-nonsense guide to picking your first pair of
  running shoes, covering fit, cushioning, terrain, and budget so beginners avoid injury.">
  <link rel="canonical" href="https://example.com/running-shoes">
  <script type="application/ld+json">{"@type": "Article"}</script>
</head>
<body>
  <h1>Best Running Shoes for Beginners</h1>
  <h2>Why Fit Matters</h2>
  <p>""" + (" ".join(["running shoes are great for beginners who want comfort and support."] * 60)) + """</p>
  <img src="shoe.jpg" alt="A pair of running shoes on pavement">
  <a href="/guides/terrain">terrain guide</a>
  <a href="https://otherblog.com/reviews">an external review</a>
</body>
</html>
"""

THIN_HTML = """
<html>
<head></head>
<body>
  <p>Too short.</p>
</body>
</html>
"""


def _check(result, check_type):
    return next(c for c in result.checks if c.check_type == check_type)


def test_well_formed_page_scores_highly():
    result = run_onpage_audit(GOOD_HTML, "https://example.com/running-shoes", target_keyword="running shoes")

    assert result.extracted_title == "Best Running Shoes for Beginners in 2026"
    assert result.score >= 70
    assert _check(result, "title_tag").status == CheckStatus.pass_
    assert _check(result, "canonical_tag").status == CheckStatus.pass_
    assert _check(result, "structured_data").status == CheckStatus.pass_
    assert _check(result, "heading_structure").status == CheckStatus.pass_


def test_missing_everything_fails_hard():
    result = run_onpage_audit(THIN_HTML, "https://example.com/empty")

    assert result.extracted_title is None
    assert _check(result, "title_tag").status == CheckStatus.fail
    assert _check(result, "meta_description").status == CheckStatus.fail
    assert _check(result, "heading_structure").status == CheckStatus.fail
    assert _check(result, "content_length").status == CheckStatus.warning
    assert result.score <= 50


def test_duplicate_title_flagged_against_siblings():
    result = run_onpage_audit(
        GOOD_HTML,
        "https://example.com/running-shoes",
        target_keyword="running shoes",
        sibling_titles=["Best Running Shoes for Beginners in 2026"],
    )

    assert _check(result, "title_tag").status == CheckStatus.fail


def test_multiple_h1_warns():
    html = GOOD_HTML.replace("<h2>Why Fit Matters</h2>", "<h1>Second H1</h1>")
    result = run_onpage_audit(html, "https://example.com/running-shoes")

    assert _check(result, "heading_structure").status == CheckStatus.warning


def test_images_without_alt_fail():
    html = GOOD_HTML.replace('<img src="shoe.jpg" alt="A pair of running shoes on pavement">', '<img src="shoe.jpg">')
    result = run_onpage_audit(html, "https://example.com/running-shoes")

    assert _check(result, "image_alt_text").status == CheckStatus.fail


def test_noindex_robots_meta_fails():
    html = GOOD_HTML.replace("<head>", '<head><meta name="robots" content="noindex">')
    result = run_onpage_audit(html, "https://example.com/running-shoes")

    assert _check(result, "robots_meta_tag").status == CheckStatus.fail
