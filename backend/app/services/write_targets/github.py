"""A git repository, written as a pull request.

For a site built from code - Next.js, Hugo, Jekyll, Astro - the content is in
files, not a database. The write is therefore a branch, a commit and a **pull
request**, never a push to the default branch: review before merge is what makes
writing into somebody's codebase acceptable at all, and it costs nothing to
offer. It also changes what "applied" means, which is why `writes_immediately`
is False here - the change is proposed, and a human merges it.

**Finding the file without knowing the framework.** Every static-site generator
answers "which file produces this URL" differently, and encoding those
conventions would mean being wrong for the next one. Instead Signal searches the
repository for the *exact current value* it just read off the live page. A title
string or a meta description is close to unique; it pins the file and the line
without any knowledge of routing. Zero matches or several is a refusal, not a
guess - editing the wrong file is worse than doing nothing.

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
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import httpx

from .base import FieldWrite, Receipt, TargetStatus, WriteTarget, WriteTargetError

API = "https://api.github.com"
TIMEOUT = 30.0
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

    def _find_file(self, client: httpx.Client, needle: str, branch: str) -> Tuple[str, str, str]:
        """(path, sha, content) of the one file containing `needle` exactly once."""
        found = self._json(
            client.get("/search/code", params={"q": f'"{needle}" repo:{self.repo}', "per_page": 20})
        )
        paths = [
            item["path"]
            for item in ((found or {}).get("items") or [])
            if isinstance(item, dict) and isinstance(item.get("path"), str)
        ]
        if not paths:
            raise WriteTargetError(
                f'Nothing in {self.repo} contains "{_short(needle)}". Either that value is generated '
                "at build time rather than written in a file, or it lives on a branch GitHub has not "
                "indexed (code search only covers the default branch)."
            )

        matches: List[Tuple[str, str, str]] = []
        for path in paths:
            try:
                content, sha = self._read_file(client, path, branch)
            except WriteTargetError:
                continue  # indexed on the default branch but absent from ours
            if content.count(needle) == 1:
                matches.append((path, sha, content))
            elif content.count(needle) > 1:
                raise WriteTargetError(
                    f'"{_short(needle)}" appears more than once in {path}. Signal will not guess '
                    "which occurrence is the one on the page."
                )

        if not matches:
            raise WriteTargetError(
                f'GitHub\'s index lists {", ".join(paths[:3])} for "{_short(needle)}", but the value is '
                f"not in any of them on {branch}. The index may be behind the branch."
            )
        if len(matches) > 1:
            raise WriteTargetError(
                f'"{_short(needle)}" is in {len(matches)} files ({", ".join(m[0] for m in matches[:3])}). '
                "Signal will not guess which one produces this page."
            )
        return matches[0]

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
                anchor = write.before
                transform = lambda text, w=write: text.replace(w.before, w.value, 1)

            edit = next((e for e in by_path.values() if anchor in e.updated), None)
            if edit is None:
                path, sha, content = self._find_file(client, anchor, branch)
                edit = by_path.get(path) or _FileEdit(path=path, sha=sha, original=content, updated=content)
                by_path[path] = edit
            edit.updated = transform(edit.updated)

        changed = [e for e in by_path.values() if e.updated != e.original]
        if not changed:
            raise WriteTargetError("Nothing in the repository needed changing - the values already match.")
        return changed

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
        return Receipt(
            ref=str(number),
            url=(pr or {}).get("html_url"),
            detail=f"Opened pull request #{number} against {base}. Merge it to apply the change.",
            extra={"branch": branch, "base": base},
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
    lines += ["", f"Files changed: {', '.join(paths)}.", "", "Merging this applies the change; closing it discards it."]
    return "\n".join(lines)


def _md_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
