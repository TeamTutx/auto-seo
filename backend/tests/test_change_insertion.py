"""Adding a tag that is not in the repository yet.

Pure text manipulation, so these are pure text tests - no GitHub, no database.
What they are really about is the *refusals*: insertion chooses a location
rather than being handed one, and the two ways that goes wrong are putting a
page's tag in a shared layout (which silently de-indexes every other page using
it) and putting a document-level tag in a file that is not a document. Both are
checked here, as is the one thing a bad JSX edit would cause that a bad
replacement never does: a file that no longer compiles.
"""
import json

import pytest

from app.services.write_targets import insertion

ONE_LINE = '''import type { Metadata } from "next";

export const metadata: Metadata = { title: "Sign in" };

export default function LoginPage() {
  return (
    <Suspense>
      <AuthForm mode="login" />
    </Suspense>
  );
}
'''

MULTI_LINE = '''import type { Metadata } from "next";
import { APP_NAME } from "@/lib/config";

export const metadata: Metadata = {
  title: { absolute: `${APP_NAME} — one resume per job` },
  description:
    "Tailor your resume to every job.",
};

export default function HomePage() {
  return (
    <div className="flex flex-col gap-10">
      <h1>Hello</h1>
    </div>
  );
}
'''

HTML = '''<!doctype html>
<html>
  <head>
    <title>About us</title>
  </head>
  <body>About</body>
</html>
'''

LD_JSON = '{"@context":"https://schema.org","@type":"WebSite","name":"Acme"}'


# --- the happy paths, one per shape Signal recognises -------------------


def test_a_canonical_goes_into_a_one_line_metadata_object():
    out = insertion.insert(ONE_LINE, "app/login/page.tsx", "canonical_tag", "https://acme.test/login/")
    assert 'title: "Sign in", alternates: { canonical: "https://acme.test/login/" } };' in out
    # The object stays on one line: there was no closing-brace line to indent to.
    assert out.count("\n") == ONE_LINE.count("\n")


def test_a_canonical_goes_into_a_multi_line_metadata_object():
    out = insertion.insert(MULTI_LINE, "app/page.tsx", "canonical_tag", "https://acme.test/")
    assert '  alternates: { canonical: "https://acme.test/" },\n};' in out
    assert "Tailor your resume to every job." in out  # nothing else moved


def test_a_description_is_added_next_to_the_title_it_belongs_with():
    out = insertion.insert(ONE_LINE, "app/login/page.tsx", "meta_description", "Sign in to Acme.")
    assert 'description: "Sign in to Acme."' in out


def test_a_tag_in_a_real_head_lines_up_with_its_siblings():
    out = insertion.insert(HTML, "src/pages/about.html", "canonical_tag", "https://acme.test/about/")
    assert '    <link rel="canonical" href="https://acme.test/about/">\n  </head>' in out


def test_a_value_with_quotes_and_ampersands_is_escaped_for_the_attribute():
    out = insertion.insert(HTML, "about.html", "meta_description", 'Tea & "scones", cheap')
    assert 'content="Tea &amp; &quot;scones&quot;, cheap"' in out


def test_json_ld_becomes_a_script_inside_the_page_root():
    out = insertion.insert(MULTI_LINE, "app/page.tsx", "structured_data", LD_JSON)
    assert '<div className="flex flex-col gap-10">' in out
    assert 'type="application/ld+json"' in out
    # The JSON travels as a JS string literal, so it needs no HTML escaping and
    # cannot be broken by a quote in the data.
    assert f"__html: {json.dumps(LD_JSON)}" in out
    assert out.index("application/ld+json") < out.index("<h1>Hello</h1>")


def test_json_ld_works_when_the_page_returns_a_fragment():
    page = MULTI_LINE.replace('<div className="flex flex-col gap-10">', "<>").replace("</div>", "</>")
    out = insertion.insert(page, "app/page.tsx", "structured_data", LD_JSON)
    assert "<>\n      {/* JSON-LD" in out


def test_json_ld_in_a_plain_html_page_goes_in_the_head_instead():
    out = insertion.insert(HTML, "about.html", "structured_data", LD_JSON)
    assert f'<script type="application/ld+json">\n{LD_JSON}\n    </script>' in out


def test_an_attribute_full_of_braces_does_not_confuse_the_root_element():
    page = MULTI_LINE.replace(
        '<div className="flex flex-col gap-10">',
        '<div className={cx("a>b", { open: true })} data-x=">">',
    )
    out = insertion.insert(page, "app/page.tsx", "structured_data", LD_JSON)
    assert 'data-x=">">\n      {/* JSON-LD' in out


# --- the refusals, which are the point ---------------------------------


@pytest.mark.parametrize("path", [
    "app/layout.tsx",
    "pages/_app.tsx",
    "pages/_document.tsx",
    "layouts/_default/baseof.html",
    "_includes/head.html",
    "themes/x/partials/header.html",
])
def test_a_shared_layout_is_never_given_a_pages_own_tag(path):
    """One canonical tag in a shared layout tells Google every page using it is
    this page. The diff looks like three added lines, so nobody reads it as
    dangerous - which is exactly why this is refused rather than reviewed."""
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(HTML, path, "canonical_tag", "https://acme.test/")
    assert "shared layout" in str(exc.value)
    assert "by hand" in str(exc.value)


def test_a_page_file_is_not_mistaken_for_a_layout():
    assert not insertion.is_shared_template("pages/index.tsx")
    assert not insertion.is_shared_template("app/page.tsx")
    assert not insertion.is_shared_template("content/about.md")


def test_a_component_that_merely_shares_the_title_is_refused():
    """"Sign in" is both the page's title and a button's label. The button's
    file is a plausible search hit and a nonsensical place for a canonical tag,
    so owning document metadata - not the path - is what qualifies a file."""
    component = 'export function AuthForm() {\n  return <button>Sign in</button>;\n}\n'
    assert not insertion.owns_document_metadata(component)
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(component, "components/auth-form.tsx", "canonical_tag", "https://acme.test/login/")
    assert "does not decide the page's <head>" in str(exc.value)


def test_markdown_content_is_refused_rather_than_given_a_guessed_front_matter_key():
    """`canonicalURL` is Hugo's spelling, `canonical` is Jekyll-plugin
    territory, and there is no portable one - so this stays a human's job."""
    markdown = "---\ntitle: About us\n---\n\nAbout our company.\n"
    with pytest.raises(insertion.CannotInsert):
        insertion.insert(markdown, "content/about.md", "canonical_tag", "https://acme.test/about/")


def test_a_key_already_in_the_metadata_is_not_duplicated():
    page = MULTI_LINE.replace("  description:", '  alternates: { canonical: "https://old.test/" },\n  description:')
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(page, "app/page.tsx", "canonical_tag", "https://acme.test/")
    assert "already sets `alternates`" in str(exc.value)


def test_structured_data_that_would_break_out_of_the_script_is_refused():
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(MULTI_LINE, "app/page.tsx", "structured_data", '{"x":"</script><b>"}')
    assert "break out" in str(exc.value)


def test_a_self_closing_root_has_nowhere_to_put_a_child():
    page = MULTI_LINE.replace('<div className="flex flex-col gap-10">\n      <h1>Hello</h1>\n    </div>', "<Thing />")
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(page, "app/page.tsx", "structured_data", LD_JSON)
    assert "self-closing" in str(exc.value)


def test_a_robots_tag_is_never_inserted():
    """A page with no robots meta tag is a page that may be indexed, which is
    the wanted state - so there is nothing to add, and the compiler never asks."""
    assert "robots_meta_tag" not in insertion.INSERTABLE
    with pytest.raises(insertion.CannotInsert):
        insertion.insert(HTML, "about.html", "robots_meta_tag", "index, follow")


def test_two_documents_in_one_file_are_not_guessed_between():
    doubled = HTML + HTML
    with pytest.raises(insertion.CannotInsert) as exc:
        insertion.insert(doubled, "about.html", "canonical_tag", "https://acme.test/about/")
    assert "2 closing </head>" in str(exc.value)
