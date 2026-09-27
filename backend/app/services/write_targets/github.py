"""A git repository, written as a pull request.

For a site built from code - Next.js, Hugo, Jekyll, Astro - the content is in
files, not a database. The write is therefore a branch, a commit and a **pull
request**, never a push to the default branch: review before merge is what makes
writing into somebody's codebase acceptable at all, and it costs nothing to
offer. It also changes what "applied" means, which is why `writes_immediately`
is False here - the change is proposed, and a human merges it.

**Finding the file without knowing the framework.** Every static-site generator
answers "which file produces this URL" differently, and encoding those
conventions would mean being wrong for the next one. Instead Signal looks through
the repository for the *exact current value* it just read off the live page. A
title string or a meta description is close to unique; it pins the file and the
line without any knowledge of routing. Zero matches or several is a refusal, not
a guess - editing the wrong file is worse than doing nothing.

**It reads the repository tarball rather than asking code search.** The first
version used `GET /search/code`, and it did not work on the first real repository
it met: GitHub's code search tokenises, so `"Signal - SEO audits, rank tracking
and AI fixes"` - an em dash and two commas - matched nothing, while the string sat
in `frontend/app/layout.tsx` all along. Its index also only covers the default
branch and lags behind pushes. `GET /repos/{repo}/tarball/{ref}` is one request,
is exactly the tree being written to, and substring matching over it is byte
comparison with no query language in between.

**Searching by value locates the line, not the page.** A title in a shared layout
serves every page that does not override it, so replacing it changes all of them
- Signal asked to fix one page and the edit moves many. There is no
framework-agnostic way to tell the two apart from the value alone, so the pull
request says so and the diff shows the file; the human merging it is the check.
This is the main reason a repository write is a pull request rather than a commit.

**The consequence: this target replaces, it does not insert.** A value Signal
cannot find is a value it cannot locate a place for, and the most common audit
failure - no meta description at all - is exactly that case. Inserting one would
mean generating framework-specific syntax at a position chosen by guesswork; a
pull request would make the mistake reviewable but would not make it right. Those
changes are refused with a reason, and the user adds the tag once by hand, after
which Signal can maintain it forever. Image alt text is the exception and works
either way, because the `src` is always there to anchor on - see _rewrite_image.
"""
import base64
import io
import re
import tarfile
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

from .base import FieldWrite, Receipt, TargetStatus, WriteTarget, WriteTargetError

API = "https://api.github.com"
TIMEOUT = 60.0  # a tarball download, not just a JSON call
MAX_TARBALL_BYTES = 80_000_000
MAX_FILE_BYTES = 2_000_000

# Paths that can hold a page's text without being what produces the page: a test
# asserting on the title, a committed build output, a vendored dependency. They
# are only ever used to break a tie - if the sole match is in one of these, it is
# still reported, because being wrong about that is better than pretending the
# value does not exist.
#
# This is a heuristic, and a deliberately narrow one. "A file under tests/ does
# not serve a web page" holds nearly everywhere; "a Next.js route lives in app/"
# does not, which is why the search never assumes anything about routing.
_IGNORED_SEGMENTS = {
    "node_modules", ".git", "dist", "build", "out", ".next", ".nuxt", ".output",
    "coverage", "vendor", "__pycache__", ".venv", "venv", "site-packages",
    "test", "tests", "__tests__", "spec", "specs", "e2e", "fixtures", "__snapshots__",
}
_IGNORED_SUFFIXES = (".lock", ".min.js", ".min.css", ".map", ".snap")
_TEST_BASENAME = re.compile(r"(^test_|_test\.|\.test\.|\.spec\.)")


def _unlikely_source(path: str) -> bool:
    """Whether this path is somewhere a page's text lives without producing it."""
    segments = path.split("/")
    if any(s in _IGNORED_SEGMENTS for s in segments[:-1]):
        return True
    name = segments[-1]
    return name.endswith(_IGNORED_SUFFIXES) or bool(_TEST_BASENAME.search(name))
BRANCH_PREFIX = "signal/seo"


@dataclass
class _FileEdit:
    path: str
    sha: str
    original: str
    updated: str


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class GitHubTarget(WriteTarget):
    kind = "github"
    #: A pull request is not a live change. The UI says "opened a pull request",
    #: not "applied", and verification waits for the merge and the next audit.
    writes_immediately = False
    supports = (
        "title_tag",
        "meta_description",
        "canonical_tag",
        "robots_meta_tag",
        "structured_data",
        "image_alt_text",
    )

    def __init__(self, repo: str, token: str, branch: str = ""):
        self.repo = repo.strip().strip("/")
        self._token = token
        self.branch = branch.strip()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=API,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    @staticmethod
    def _json(response: httpx.Response) -> object:
        if response.status_code == 401:
            raise WriteTargetError("GitHub rejected the token. It may have been revoked, or have expired.")
        if response.status_code == 403:
            message = ""
            try:
                message = (response.json() or {}).get("message", "")
            except ValueError:
                pass
            if "rate limit" in message.lower():
                raise WriteTargetError("GitHub's rate limit is exhausted for this token. Try again shortly.")
            raise WriteTargetError(
                "The token is valid but not allowed to do this. It needs Contents: read and write "
                "and Pull requests: read and write on this repository."
            )
        if response.status_code == 404:
            raise WriteTargetError(
                f"GitHub has no {response.request.url.path} - check the repository name, and that the "
                "token has access to it (a fine-grained token must list the repository explicitly)."
            )
        if response.status_code == 422:
            detail = response.text[:300]
            raise WriteTargetError(f"GitHub refused the change as invalid: {detail}")
        if response.status_code >= 400:
            raise WriteTargetError(f"GitHub returned {response.status_code}: {response.text[:200]}")
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise WriteTargetError("GitHub's reply was not JSON.")

    # --- connect-time check ---

    def test(self) -> TargetStatus:
        try:
            with self._client() as client:
                repo = self._json(client.get(f"/repos/{self.repo}"))
        except WriteTargetError as exc:
            return TargetStatus(ok=False, detail=str(exc))
        except httpx.HTTPError as exc:
            return TargetStatus(ok=False, detail=f"Could not reach GitHub: {exc}")

        if not isinstance(repo, dict):
            return TargetStatus(ok=False, detail="GitHub did not describe that repository.")
        if not (repo.get("permissions") or {}).get("push"):
            return TargetStatus(
                ok=False,
                detail=(
                    "The token can read this repository but not write to it. It needs Contents: "
                    "read and write, and Pull requests: read and write."
                ),
            )
        default = repo.get("default_branch") or "main"
        branch = self.branch or default
        return TargetStatus(
            ok=True,
            detail=(
                f"Connected to {repo.get('full_name')}. Changes will open a pull request against "
                f"{branch}, for you to review and merge."
            ),
            capabilities=list(self.supports),
        )

    # --- locating the text to change ---

    def _base_branch(self, client: httpx.Client) -> str:
        if self.branch:
            return self.branch
        repo = self._json(client.get(f"/repos/{self.repo}"))
        return (repo or {}).get("default_branch") or "main"

    def _text_files(self, client: httpx.Client, branch: str) -> Dict[str, str]:
        """Every UTF-8 text file in the repo at `branch`, keyed by path.

        Downloaded once per write and reused for every field, so a pull request
        touching three values costs one tarball rather than three searches."""
        response = client.get(f"/repos/{self.repo}/tarball/{branch}")
        if response.status_code >= 400:
            self._json(response)  # raises with a readable reason

        declared = response.headers.get("content-length")
        if declared and int(declared) > MAX_TARBALL_BYTES:
            raise WriteTargetError(
                f"{self.repo} is {int(declared) // 1_000_000}MB compressed, larger than the "
                f"{MAX_TARBALL_BYTES // 1_000_000}MB Signal will download to find a value in it."
            )
        if len(response.content) > MAX_TARBALL_BYTES:
            raise WriteTargetError(f"{self.repo} is too large for Signal to search.")

        files: Dict[str, str] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(response.content), mode="r:gz") as archive:
                for member in archive:
                    if not member.isfile() or member.size > MAX_FILE_BYTES:
                        continue
                    handle = archive.extractfile(member)
                    if handle is None:
                        continue
                    try:
                        text = handle.read().decode("utf-8")
                    except (UnicodeDecodeError, OSError):
                        continue  # a binary or unreadable file is never one we edit
                    # GitHub wraps everything in <owner>-<repo>-<sha>/; strip it so
                    # paths match what the Contents API expects.
                    _, _, path = member.name.partition("/")
                    if path:
                        files[path] = text
        except tarfile.TarError as exc:
            raise WriteTargetError(f"Could not read {self.repo}'s contents from GitHub: {exc}")
        return files

    def _find_file(self, needle: str, files: Dict[str, str], branch: str) -> Tuple[str, str]:
        """(path, occurrences) for the one file holding `needle`."""
        matches = {path: text.count(needle) for path, text in files.items() if needle in text}

        if not matches:
            raise WriteTargetError(
                f'Nothing in {self.repo} on {branch} contains "{_short(needle)}", so there is no line '
                "to change. That usually means the value is assembled at build time rather than "
                "written in a file."
            )

        # A test asserting on the title, or a committed build output, holds the
        # same string without being the thing that serves it. Discount those
        # before giving up - but only as a tie-breaker, never to hide the only
        # match there is.
        if len(matches) > 1:
            likely = {p: c for p, c in matches.items() if not _unlikely_source(p)}
            if likely:
                matches = likely

        if len(matches) > 1:
            listed = ", ".join(sorted(matches)[:4])
            raise WriteTargetError(
                f'"{_short(needle)}" is in {len(matches)} files that all look like sources '
                f"({listed}). Signal will not guess which one produces this page - remove the "
                "duplicate, or change this value by hand."
            )

        path, count = next(iter(matches.items()))
        if count > 1:
            raise WriteTargetError(
                f'"{_short(needle)}" appears {count} times in {path}. Signal will not guess which '
                "occurrence is the one on the page."
            )
        return path, count

    def _read_file(self, client: httpx.Client, path: str, branch: str) -> Tuple[str, str]:
        data = self._json(client.get(f"/repos/{self.repo}/contents/{path}", params={"ref": branch}))
        if not isinstance(data, dict) or data.get("encoding") != "base64":
            raise WriteTargetError(f"{path} is not a file Signal can read as text.")
        try:
            content = base64.b64decode(data["content"]).decode()
        except (KeyError, ValueError, UnicodeDecodeError):
            raise WriteTargetError(f"{path} is not UTF-8 text, so Signal will not edit it.")
        return content, data["sha"]

    # --- the edits ---

    def _plan_edits(self, client: httpx.Client, writes: List[FieldWrite], branch: str) -> List[_FileEdit]:
        files = self._text_files(client, branch)
        by_path: Dict[str, _FileEdit] = {}
        for write in writes:
            # The lambdas bind `write` explicitly: they happen to be called
            # inside this same iteration today, but a closure over a loop
            # variable is one refactor away from applying the last write's value
            # to every file.
            if write.field == "image_alt_text":
                anchor = write.subject
                transform = lambda text, w=write: _rewrite_image(text, w.subject, w.value)
            else:
                if not (write.before or "").strip():
                    raise WriteTargetError(
                        f"This page has no {write.field.replace('_', ' ')} for Signal to find in the "
                        "repository, so there is nowhere to put the new one. Add the tag once by hand "
                        "and Signal can keep it up to date after that."
                    )
                if write.before not in "\n".join(files.values()):
                    self._explain_missing(write, files)
                anchor = write.before
                transform = lambda text, w=write: text.replace(w.before, w.value, 1)

            edit = next((e for e in by_path.values() if anchor in e.updated), None)
            if edit is None:
                path, _ = self._find_file(anchor, files, branch)
                if path not in by_path:
                    # Located from the tarball, but read and written through the
                    # Contents API: that is the copy the commit is based on, and
                    # it carries the blob sha the update needs.
                    content, sha = self._read_file(client, path, branch)
                    if anchor not in content:
                        raise WriteTargetError(
                            f'"{_short(anchor)}" is in {path} in the downloaded tree but not in the '
                            f"copy GitHub is serving for {branch} - the branch moved while Signal was "
                            "reading it. Try again."
                        )
                    by_path[path] = _FileEdit(path=path, sha=sha, original=content, updated=content)
                edit = by_path[path]
            edit.updated = transform(edit.updated)

        changed = [e for e in by_path.values() if e.updated != e.original]
        if not changed:
            raise WriteTargetError("Nothing in the repository needed changing - the values already match.")
        return changed

    def _explain_missing(self, write: FieldWrite, files: Dict[str, str]) -> None:
        """Raise the right reason for a value the repository does not contain.

        "Not in any file" and "a merged pull request already replaced it" look
        identical from the live page, and the answers are opposites: one means
        Signal can never write this field, the other means wait for the deploy.
        A value Signal itself wrote sitting in the tree settles which it is."""
        for earlier in write.previously_wrote:
            if earlier and any(earlier in text for text in files.values()):
                raise WriteTargetError(
                    f"{self.repo} already has the {write.field.replace('_', ' ')} Signal wrote in an "
                    "earlier pull request, but your site is still serving the one before it - it has "
                    "not rebuilt since that pull request was merged. Wait for the deploy to finish, "
                    "rescan the page, and write this fix again so it is based on what is published."
                )

    def write(self, page_url: str, writes: List[FieldWrite]) -> Receipt:
        with self._client() as client:
            base = self._base_branch(client)
            edits = self._plan_edits(client, writes, base)

            head_sha = ((self._json(client.get(f"/repos/{self.repo}/git/ref/heads/{base}")) or {}).get("object") or {}).get("sha")
            if not head_sha:
                raise WriteTargetError(f"Could not read the head of {base}.")

            branch = f"{BRANCH_PREFIX}/{datetime.utcnow():%Y%m%d-%H%M%S}"
            self._json(client.post(f"/repos/{self.repo}/git/refs", json={"ref": f"refs/heads/{branch}", "sha": head_sha}))

            summary = ", ".join(sorted({w.field.replace("_", " ") for w in writes}))
            for edit in edits:
                self._json(client.put(
                    f"/repos/{self.repo}/contents/{edit.path}",
                    json={
                        "message": f"SEO: update {summary} for {page_url}",
                        "content": _b64(edit.updated),
                        "sha": edit.sha,
                        "branch": branch,
                    },
                ))

            body = _pr_body(page_url, writes, [e.path for e in edits])
            pr = self._json(client.post(
                f"/repos/{self.repo}/pulls",
                json={"title": f"SEO: {summary} for {page_url}", "head": branch, "base": base, "body": body},
            ))

        number = (pr or {}).get("number")
        changed = ", ".join(e.path for e in edits)
        return Receipt(
            ref=str(number),
            url=(pr or {}).get("html_url"),
            detail=(
                f"Opened pull request #{number} against {base}, changing {changed}. "
                "Check the diff before merging: one string in a source file can be shared by more "
                "than one page."
            ),
            extra={"branch": branch, "base": base, "paths": changed},
        )

    def revert(self, page_url: str, writes: List[FieldWrite], receipt: Optional[dict]) -> Receipt:
        """Undo depends on whether a human merged it yet: an open pull request is
        closed, a merged one is reversed by a second pull request. Nothing is
        force-pushed and no history is rewritten."""
        number = (receipt or {}).get("ref")
        if not number:
            raise WriteTargetError("Signal has no pull request recorded for this change, so there is nothing to close.")

        with self._client() as client:
            pr = self._json(client.get(f"/repos/{self.repo}/pulls/{number}"))
            merged = bool((pr or {}).get("merged"))
            state = (pr or {}).get("state")

            if not merged:
                if state == "closed":
                    return Receipt(ref=str(number), url=(pr or {}).get("html_url"), detail=f"Pull request #{number} was already closed.")
                self._json(client.patch(f"/repos/{self.repo}/pulls/{number}", json={"state": "closed"}))
                branch = ((receipt or {}).get("extra") or {}).get("branch")
                if branch:
                    client.delete(f"/repos/{self.repo}/git/refs/heads/{branch}")  # tidy-up; failure is not worth an error
                return Receipt(
                    ref=str(number),
                    url=(pr or {}).get("html_url"),
                    detail=f"Closed pull request #{number}. Nothing reached {(receipt or {}).get('extra', {}).get('base', 'the branch')}.",
                )

        reverse = self.write(page_url, writes)
        return Receipt(
            ref=reverse.ref,
            url=reverse.url,
            detail=f"Pull request #{number} was already merged, so #{reverse.ref} puts the previous values back.",
            extra=reverse.extra,
        )


def _short(value: str, limit: int = 60) -> str:
    value = " ".join((value or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _rewrite_image(text: str, src: str, alt: str) -> str:
    """Set the alt text on whichever image references `src`.

    Works on an HTML or JSX `<img>` (adding the attribute when it is missing, or
    replacing an empty one) and on a Markdown image, where the alt text is the
    bracketed part. The `src` is the anchor, so unlike every other field this one
    does not need an existing value to replace."""
    escaped = re.escape(src)

    md = re.compile(r"!\[[^\]]*\]\(\s*" + escaped + r"[^)]*\)")
    match = md.search(text)
    if match:
        return text[: match.start()] + _md_with_alt(match.group(0), alt) + text[match.end():]

    tag = re.compile(r"<img\b[^>]*?" + escaped + r"[^>]*?>", re.IGNORECASE | re.DOTALL)
    match = tag.search(text)
    if not match:
        raise WriteTargetError(f"Found {src} in the file, but not inside an <img> tag or a Markdown image.")
    return text[: match.start()] + _tag_with_alt(match.group(0), alt) + text[match.end():]


def _escape_md(alt: str) -> str:
    return alt.replace("]", r"\]")


def _md_with_alt(image: str, alt: str) -> str:
    return "![" + _escape_md(alt) + image[image.index("]"):]


def _tag_with_alt(tag: str, alt: str) -> str:
    quoted = alt.replace('"', "&quot;")
    existing = re.search(r"\salt\s*=\s*(\"[^\"]*\"|'[^']*'|\{[^}]*\})", tag, re.IGNORECASE)
    if existing:
        return tag[: existing.start()] + f' alt="{quoted}"' + tag[existing.end():]
    closing = re.search(r"\s*/?>$", tag)
    return tag[: closing.start()] + f' alt="{quoted}"' + tag[closing.start():]


def _pr_body(page_url: str, writes: List[FieldWrite], paths: List[str]) -> str:
    lines = [
        f"Opened by [Signal](https://signal-seo.in) for **{page_url}**.",
        "",
        "| Field | Before | After |",
        "| --- | --- | --- |",
    ]
    for write in writes:
        before = _short(write.before or "", 80) or "_(not set)_"
        lines.append(f"| {write.field.replace('_', ' ')} | {_md_cell(before)} | {_md_cell(_short(write.value, 80))} |")
    lines += [
        "",
        f"Files changed: {', '.join(paths)}.",
        "",
        "> **Check what else uses these values.** Signal found this text by searching the "
        "repository for what is on the live page, which locates the right line without knowing "
        "your framework - but a string in a shared layout or template serves every page that "
        "does not override it, and this change would move all of them. The diff above is the "
        "whole change; nothing is applied until you merge.",
        "",
        "Merging this applies the change; closing it discards it.",
    ]
    return "\n".join(lines)


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
