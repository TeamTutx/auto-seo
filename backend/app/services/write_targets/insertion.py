"""Adding a tag the repository does not have yet.

The replacement path next door (see github.py) finds a file by searching the
tree for the *exact current value* it read off the live page. That is what makes
it framework-agnostic, and it is also why it cannot add anything: the most
common audit failure is a tag that is simply absent, and an absent value anchors
on nothing.

Insertion needs two questions answered that replacement gets for free - **which
file**, and **where in it** - and the whole design here is about answering both
from evidence rather than from a list of framework conventions.

**Which file: anchor on a value the page does have.** A page that has no
canonical tag still has a title, a description, an h1. Those strings are in the
repository, and `github.GitHubTarget._locate` pins them to one file with the
same machinery (and the same refusals on zero or several matches) that the
replacement path uses. So the file is located by evidence, not by guessing that
a Next.js route lives under `app/`.

**Where in it: only into a file that already owns document-level metadata.**
Proven by the file containing `</head>` or an `export const metadata` object -
not by its path. A component with a "Sign in" button can match the title of the
sign-in page, and inserting a canonical tag into it would be nonsense; such a
file owns no metadata, so it is refused. This one rule replaces a pile of
per-framework path heuristics and is the reason insertion is safe to offer.

**Never into a shared layout.** This matters far more for insertion than for
replacement. A replaced title in a shared layout changes several pages' titles -
bad, and visible in the diff. A canonical tag in a shared layout tells Google
that every page using that layout *is* this page, which de-indexes all the
others. The damage is silent and it is not a diff anyone reads as dangerous, so
`is_shared_template` refuses by path and the user is told to add it by hand -
which is exactly the behaviour they had before insertion existed, so the
fallback costs nothing.

**What it will not do.** Rewrite a value that is already there (that is the
replacement path's job, and a key already present is refused rather than
duplicated), guess at Markdown front matter keys (`canonicalURL` is Hugo's,
`canonical` is not universal), or delete what it added - see
`GitHubTarget.revert`, which closes an unmerged pull request and otherwise says
plainly that removing added lines is a human's call.
"""
import json
import re
from typing import List

#: Fields that can be added where none exists. `robots_meta_tag` is absent from
#: this list on purpose: a *missing* robots tag is not a fault (it means "index
#: this", which is what you want), so the compiler never proposes one.
#: `image_alt_text` is absent because it never needed insertion - the `src` is
#: always there to anchor on.
INSERTABLE = ("title_tag", "meta_description", "canonical_tag", "structured_data")


class CannotInsert(Exception):
    """No safe place for this tag, with a sentence for whoever clicked the
    button. Separate from WriteTargetError so this module stays free of the
    GitHub target and can be tested as the text manipulation it is."""


def label(field: str) -> str:
    return field.replace("_", " ")


# --- the two gates -------------------------------------------------------

# Names that mean "this file wraps other files", across the generators Signal
# actually meets. Deliberately as narrow as _unlikely_source in github.py:
# every entry is a filename whose job is to be shared, in some framework's
# documented convention. `index` is *not* here - `pages/index.tsx` is a single
# real page.
_SHARED_BASENAME = re.compile(
    r"^(layout|template|_app|_document|base|baseof|default|head|header|footer|nav|navbar)\.",
    re.I,
)
_SHARED_SEGMENTS = {
    "layouts", "_layouts", "_includes", "includes", "partials", "_partials",
    "templates", "_templates",
}


def is_shared_template(path: str) -> bool:
    """Whether this file serves pages other than the one being fixed."""
    segments = path.split("/")
    if any(s.lower() in _SHARED_SEGMENTS for s in segments[:-1]):
        return True
    return bool(_SHARED_BASENAME.match(segments[-1]))


_HEAD_CLOSE = re.compile(r"[ \t]*</head\s*>", re.I)
_METADATA_DECL = re.compile(r"\bexport\s+(?:const|let|var)\s+metadata\b")


def owns_document_metadata(text: str) -> bool:
    """Whether this file is somewhere a page's own <head> is decided.

    The gate that keeps a document-level tag out of a component that merely
    happens to contain the same words as the page's title."""
    return bool(_HEAD_CLOSE.search(text) or _METADATA_DECL.search(text))


def check_destination(path: str, text: str, field: str) -> None:
    """Whether this file may receive `field`, or CannotInsert with why not.

    Separate from `insert` so a caller can ask before committing to a file. It
    matters because the answer "no" is usually a reason to keep looking: a page
    with no description of its own serves the layout's, so searching for the
    description finds the layout - while the page's own title still finds the
    page. Checking only at the point of editing would turn that into a refusal."""
    if field not in INSERTABLE:
        raise CannotInsert(
            f"Signal does not add a {label(field)} that was never there - it would have no way to "
            "tell where it belongs."
        )
    if is_shared_template(path):
        raise CannotInsert(
            f"{path} looks like a shared layout or template, so it serves other pages too. "
            f"Adding a {label(field)} there would give all of them this page's tag - which, for a "
            "canonical tag, tells Google they are all the same page. Add it to this page's own "
            "file by hand and Signal can keep it up to date after that."
        )
    if not owns_document_metadata(text):
        raise CannotInsert(
            f"{path} is where this page's text lives, but it does not decide the page's <head> - "
            "there is no closing </head> and no exported metadata in it. Signal will not put a "
            f"{label(field)} somewhere it cannot tell it belongs. Add the tag by hand to whichever "
            "file owns this page's head, and Signal can keep it up to date after that."
        )


def insert(text: str, path: str, field: str, value: str) -> str:
    """`text` with `field` added, or CannotInsert with the reason why not."""
    check_destination(path, text, field)
    if _HEAD_CLOSE.search(text):
        return _into_head(text, field, value)
    if field == "structured_data":
        return _into_jsx(text, value)
    return _into_metadata(text, field, value)


# --- HTML, and anything with a real <head> -------------------------------


def _attr(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def _escaped(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_HEAD_TAG = {
    "canonical_tag": lambda v: f'<link rel="canonical" href="{_attr(v)}">',
    "meta_description": lambda v: f'<meta name="description" content="{_attr(v)}">',
    "title_tag": lambda v: f"<title>{_escaped(v)}</title>",
}


def _into_head(text: str, field: str, value: str) -> str:
    closers = list(_HEAD_CLOSE.finditer(text))
    if len(closers) != 1:
        raise CannotInsert(
            f"This file has {len(closers)} closing </head> tags, so Signal cannot tell which "
            f"document the {label(field)} belongs to."
        )
    at = closers[0]
    closing_indent = re.match(r"[ \t]*", at.group(0)).group(0)
    # Line up with whatever is already in the head rather than with </head>
    # itself, which sits one level out.
    previous = text.rfind("\n", 0, at.start())
    sibling = re.match(r"[ \t]*", text[previous + 1 :]).group(0) if previous >= 0 else ""
    indent = sibling if len(sibling) > len(closing_indent) else closing_indent + "  "
    if field == "structured_data":
        _reject_script_break(value)
        snippet = f'<script type="application/ld+json">\n{value}\n{indent}</script>'
    else:
        snippet = _HEAD_TAG[field](value)
    return f"{text[:at.start()]}{indent}{snippet}\n{text[at.start():]}"


# --- an exported metadata object (Next.js App Router, Nuxt) --------------

_METADATA_KEY = {
    "canonical_tag": "alternates",
    "meta_description": "description",
    "title_tag": "title",
}
_METADATA_ENTRY = {
    # Written as a literal rather than composed from a base URL: the value is
    # the URL Search Console canonicalised, and a canonical built from an
    # environment variable points at localhost in any build that forgets to set
    # it - which de-indexes the site rather than failing loudly.
    "canonical_tag": lambda v: f"alternates: {{ canonical: {_js(v)} }}",
    "meta_description": lambda v: f"description: {_js(v)}",
    "title_tag": lambda v: f"title: {_js(v)}",
}


def _js(value: str) -> str:
    """`value` as a JS/TS string literal. json.dumps is exactly right here -
    JSON string syntax is a subset of JavaScript's."""
    return json.dumps(value)


def _into_metadata(text: str, field: str, value: str) -> str:
    declaration = _METADATA_DECL.search(text)
    if not declaration:
        raise CannotInsert("This file exports no metadata object to add to.")
    open_at, close_at = _object_span(text, declaration.end())
    inner = text[open_at + 1 : close_at]

    key = _METADATA_KEY[field]
    if re.search(r"(?:^|[\s,{])" + key + r"\s*:", inner):
        raise CannotInsert(
            f"This page's metadata already sets `{key}`, but the live page shows no "
            f"{label(field)} - so the two disagree and Signal will not add a second one. "
            "Check that file by hand."
        )
    entry = _METADATA_ENTRY[field](value)

    # A one-line object (`= { title: "Sign in" };`) has no closing-brace line to
    # indent against, so it stays on one line.
    if "\n" not in inner:
        head = text[:close_at].rstrip()
        separator = "" if head.endswith("{") else ", "
        return f"{head}{separator}{entry} {text[close_at:]}"

    line_start = text.rfind("\n", open_at, close_at) + 1
    indent = re.match(r"[ \t]*", text[line_start:close_at]).group(0)
    head = text[:line_start]
    trimmed = head.rstrip()
    if not trimmed.endswith(("{", ",")):
        head = trimmed + "," + head[len(trimmed) :]
    return f"{head}{indent}  {entry},\n{text[line_start:]}"


# --- JSON-LD into a component's JSX -------------------------------------
#
# Structured data has no metadata-object key: in an App Router page the
# documented way to ship JSON-LD is to render a <script> in the component. So
# this is the one insertion that edits markup rather than a config object, and
# it is correspondingly strict - it finds the default export's `return (`, the
# root element's opening tag, and inserts one child immediately after it. Every
# shape it does not recognise is a refusal, because a bad guess here is a file
# that does not compile.

_DEFAULT_EXPORT = re.compile(r"\bexport\s+default\s+(?:async\s+)?function\b")
_RETURN_OPEN = re.compile(r"\breturn\s*\(")


def _reject_script_break(value: str) -> None:
    """A `</script` inside the JSON would end the script element early, and no
    amount of JSON or JS escaping prevents that - the HTML parser sees it first."""
    if re.search(r"</\s*script", value, re.I):
        raise CannotInsert(
            "This structured data contains a closing </script> tag, which would break out of the "
            "script element. Signal will not write it."
        )


def _into_jsx(text: str, value: str) -> str:
    _reject_script_break(value)
    exported = _DEFAULT_EXPORT.search(text)
    if not exported:
        raise CannotInsert(
            "This file has exported metadata but no default-exported component, so there is no "
            "markup for Signal to add the JSON-LD script to."
        )
    returned = _RETURN_OPEN.search(text, exported.end())
    if not returned:
        raise CannotInsert(
            "Signal could not find a `return (` in this page's component, so it cannot tell where "
            "the markup begins. Paste the JSON-LD in by hand - the value is ready above."
        )

    at = _skip_blanks(text, returned.end())
    if text[at : at + 1] != "<":
        raise CannotInsert(
            "This page's component does not return markup directly, so Signal cannot tell where "
            "the JSON-LD script would go."
        )
    after_open = at + 2 if text[at : at + 2] == "<>" else _opening_tag_end(text, at)

    line_start = text.rfind("\n", 0, at) + 1
    indent = re.match(r"[ \t]*", text[line_start:]).group(0)
    snippet = (
        f"\n{indent}  {{/* JSON-LD for search engines, added by Signal. Edit or delete it here. */}}"
        f"\n{indent}  <script"
        f'\n{indent}    type="application/ld+json"'
        f"\n{indent}    dangerouslySetInnerHTML={{{{ __html: {_js(value)} }}}}"
        f"\n{indent}  />"
    )
    return text[:after_open] + snippet + text[after_open:]


def _opening_tag_end(text: str, start: int) -> int:
    """Index just past the `>` that closes the element opening at `start`.

    Balances the `{}` of JSX expressions and skips quoted strings, so
    `<div className={cx("a>b")}>` ends at the right `>`."""
    depth = 0
    i = start + 1
    while i < len(text):
        char = text[i]
        if char in "\"'`":
            i = _skip_quoted(text, i)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        elif char == ">" and depth == 0:
            if text[start:i].rstrip().endswith("/"):
                raise CannotInsert(
                    "This page's root element is self-closing, so it has nowhere to put a child. "
                    "Paste the JSON-LD in by hand."
                )
            return i + 1
        i += 1
    raise CannotInsert("Signal could not find the end of this page's root element.")


# --- scanners -----------------------------------------------------------


def _skip_quoted(text: str, start: int) -> int:
    """Index just past the string literal starting at `start`.

    A template literal is skipped whole, `${...}` included, which is what brace
    balancing wants. A backtick nested inside a `${...}` would end the skip
    early; the callers all refuse rather than guess when the scan then fails to
    find what it expects, so that case is a refusal and not a bad edit."""
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    raise CannotInsert("This file has an unterminated string in it, so Signal will not edit it.")


def _skip_blanks(text: str, start: int) -> int:
    """Index of the next thing that is not whitespace or a comment."""
    i = start
    while i < len(text):
        if text[i].isspace():
            i += 1
            continue
        if text[i : i + 2] == "//":
            end = text.find("\n", i)
            i = len(text) if end < 0 else end + 1
            continue
        if text[i : i + 2] == "/*":
            end = text.find("*/", i + 2)
            if end < 0:
                raise CannotInsert("This file has an unterminated comment in it.")
            i = end + 2
            continue
        if text[i : i + 2] == "{/":  # a JSX comment, {/* ... */}
            end = text.find("*/}", i)
            if end < 0:
                break
            i = end + 3
            continue
        return i
    return i


def _object_span(text: str, start: int) -> tuple:
    """(open, close) indices of the `{ ... }` literal at or after `start`."""
    open_at = text.find("{", start)
    if open_at < 0:
        raise CannotInsert("Signal could not find the metadata object in this file.")
    depth = 0
    i = open_at
    while i < len(text):
        char = text[i]
        if char in "\"'`":
            i = _skip_quoted(text, i)
            continue
        if char == "/" and text[i + 1 : i + 2] in ("/", "*"):
            i = _skip_blanks(text, i)
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return open_at, i
        i += 1
    raise CannotInsert("This file's metadata object has no closing brace that Signal could find.")
