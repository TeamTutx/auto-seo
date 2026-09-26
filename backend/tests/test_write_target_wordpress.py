"""The WordPress write path.

Driven by httpx.MockTransport rather than a live site, so what these prove is the
protocol: which endpoints get called, which payload is sent, and - the ones that
matter most - the refusals. No live WordPress was available, so the capability
probe and the silently-dropped-meta case are specified here from WordPress's
documented behaviour and need confirming against a real install before the UI
promises that titles and descriptions are writable anywhere.
"""
import json

import httpx
import pytest

from app.services.write_targets import WriteTargetError
from app.services.write_targets.wordpress import ALWAYS_SUPPORTED, WordPressTarget

BASE = "https://blog.test"


def _target(handler, capabilities=None):
    target = WordPressTarget(BASE, "bob", "app pass word", capabilities=capabilities)
    target._client = lambda: httpx.Client(
        base_url=f"{BASE}/wp-json/wp/v2",
        transport=httpx.MockTransport(handler),
        headers={"Authorization": target._auth_header()},
    )
    return target


def _json_response(payload, status_code=200):
    return httpx.Response(status_code, json=payload)


# --- the credential, and what it can do ---


def test_a_fresh_target_claims_only_what_core_guarantees():
    """Before a probe has run, assuming an SEO plugin is present would produce a
    button that fails in front of the user."""
    assert WordPressTarget(BASE, "bob", "pw").supports == ALWAYS_SUPPORTED


def test_the_probe_reports_the_seo_fields_it_actually_found():
    def handler(request):
        if request.url.path.endswith("/users/me"):
            return _json_response({"name": "Bob"})
        return _json_response([{"id": 1, "meta": {"_yoast_wpseo_metadesc": "", "_yoast_wpseo_title": ""}}])

    status = _target(handler).test()

    assert status.ok
    assert set(status.capabilities) == {"image_alt_text", "meta_description", "title_tag"}
    assert "Bob" in status.detail


def test_a_wordpress_without_writable_seo_meta_says_so_plainly():
    """The honest outcome, not an error: alt text still works, and the user is
    told the rest has to be pasted in."""
    def handler(request):
        if request.url.path.endswith("/users/me"):
            return _json_response({"name": "Bob"})
        return _json_response([{"id": 1, "meta": {}}])

    status = _target(handler).test()

    assert status.ok
    assert status.capabilities == list(ALWAYS_SUPPORTED)
    assert "pasted in" in status.detail


def test_a_rejected_password_is_a_readable_failure_not_an_exception():
    status = _target(lambda request: httpx.Response(401, json={"code": "invalid_username"})).test()

    assert status.ok is False
    assert "application password" in status.detail.lower()


def test_a_url_that_is_not_wordpress_says_that_rather_than_crashing():
    status = _target(lambda request: httpx.Response(200, text="<html>a normal website</html>")).test()

    assert status.ok is False
    assert "not be a WordPress site" in status.detail


# --- writing ---


def test_a_title_is_written_to_the_seo_plugins_field_not_the_post_title():
    """A WordPress post title is the visible H1 and only part of the rendered
    <title>. Writing the suggested title tag into it would change the heading and
    still not produce the string the audit asked for."""
    sent = {}

    def handler(request):
        if request.method == "GET":
            return _json_response([
                {"id": 7, "link": f"{BASE}/about/", "meta": {"_yoast_wpseo_title": "old"}}
            ])
        sent["url"] = str(request.url)
        sent["body"] = json.loads(request.content)
        return _json_response({"id": 7, "link": f"{BASE}/about/", "meta": sent["body"]["meta"]})

    from app.services.write_targets import FieldWrite

    receipt = _target(handler, capabilities=["title_tag"]).write(
        f"{BASE}/about", [FieldWrite(field="title_tag", value="Widgets That Work", before="old")]
    )

    assert sent["body"] == {"meta": {"_yoast_wpseo_title": "Widgets That Work"}}
    assert "pages/7" in sent["url"] or "posts/7" in sent["url"]
    assert receipt.ref.endswith(":7")


def test_wordpress_accepting_the_call_but_dropping_the_meta_is_a_failure():
    """WordPress answers 200 and quietly discards meta it does not consider
    registered, so a successful status is not evidence the value landed. Without
    reading it back, Signal would report a fix it had not made."""
    def handler(request):
        if request.method == "GET":
            return _json_response([{"id": 7, "link": f"{BASE}/about/", "meta": {"rank_math_description": "old"}}])
        return _json_response({"id": 7, "meta": {"rank_math_description": "old"}})  # unchanged

    from app.services.write_targets import FieldWrite

    with pytest.raises(WriteTargetError, match="did not store"):
        _target(handler, capabilities=["meta_description"]).write(
            f"{BASE}/about", [FieldWrite(field="meta_description", value="A new description", before="old")]
        )


def test_a_field_with_no_writable_key_is_refused_with_somewhere_to_go():
    def handler(request):
        return _json_response([{"id": 7, "link": f"{BASE}/about/", "meta": {}}])

    from app.services.write_targets import FieldWrite

    with pytest.raises(WriteTargetError, match="Copy the value in instead"):
        _target(handler, capabilities=["meta_description"]).write(
            f"{BASE}/about", [FieldWrite(field="meta_description", value="new", before=None)]
        )


def test_a_permalink_is_matched_despite_scheme_and_trailing_slash():
    def handler(request):
        if request.method == "GET":
            return _json_response([{"id": 9, "link": "http://www.blog.test/about", "meta": {"_yoast_wpseo_title": ""}}])
        return _json_response({"id": 9, "meta": json.loads(request.content)["meta"]})

    from app.services.write_targets import FieldWrite

    receipt = _target(handler, capabilities=["title_tag"]).write(
        "https://blog.test/about/", [FieldWrite(field="title_tag", value="New", before="")]
    )
    assert receipt.ref.endswith(":9")


def test_several_possible_pages_and_no_exact_match_is_a_refusal():
    """Editing the wrong page is worse than doing nothing."""
    def handler(request):
        return _json_response([
            {"id": 1, "link": f"{BASE}/about-us/", "meta": {}},
            {"id": 2, "link": f"{BASE}/about-me/", "meta": {}},
        ])

    from app.services.write_targets import FieldWrite

    with pytest.raises(WriteTargetError, match="will not guess"):
        _target(handler, capabilities=["title_tag"]).write(
            f"{BASE}/about", [FieldWrite(field="title_tag", value="New", before="old")]
        )


def test_a_page_wordpress_does_not_have_says_it_may_be_generated():
    def handler(request):
        return _json_response([])

    from app.services.write_targets import FieldWrite

    with pytest.raises(WriteTargetError, match="page builder"):
        _target(handler, capabilities=["title_tag"]).write(
            f"{BASE}/about", [FieldWrite(field="title_tag", value="New", before="old")]
        )


# --- alt text, which is core and always works ---


def test_alt_text_matches_the_media_item_behind_a_resized_copy():
    """WordPress serves cat-300x200.png from the media item for cat.png, and the
    alt text belongs to the item, not the copy."""
    sent = {}

    def handler(request):
        if request.method == "GET":
            return _json_response([{"id": 42, "source_url": f"{BASE}/uploads/cat.png"}])
        sent["path"] = request.url.path
        sent["body"] = json.loads(request.content)
        return _json_response({"id": 42, "alt_text": sent["body"]["alt_text"]})

    from app.services.write_targets import FieldWrite

    receipt = _target(handler).write(
        f"{BASE}/about",
        [FieldWrite(field="image_alt_text", value="A ginger cat", subject=f"{BASE}/uploads/cat-300x200.png")],
    )

    assert sent["path"] == "/wp-json/wp/v2/media/42"
    assert sent["body"] == {"alt_text": "A ginger cat"}
    assert "42" in receipt.ref


def test_reverting_writes_the_previous_value_back():
    sent = []

    def handler(request):
        if request.method == "GET":
            return _json_response([{"id": 7, "link": f"{BASE}/about/", "meta": {"_yoast_wpseo_title": "current"}}])
        body = json.loads(request.content)
        sent.append(body)
        return _json_response({"id": 7, "meta": body["meta"]})

    from app.services.write_targets import FieldWrite

    receipt = _target(handler, capabilities=["title_tag"]).revert(
        f"{BASE}/about", [FieldWrite(field="title_tag", value="the original", before="what signal wrote")], None
    )

    assert sent == [{"meta": {"_yoast_wpseo_title": "the original"}}]
    assert "Restored" in receipt.detail
