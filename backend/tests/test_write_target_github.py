"""The GitHub write path.

Driven by httpx.MockTransport: no repository is touched and no pull request is
opened. What these prove is the sequence (search, read, branch, commit, pull
request) and, more importantly, that every case where Signal cannot be certain
which text to change is a refusal rather than a guess - because the failure mode
is editing the wrong file in somebody's codebase.
"""
import base64
import json

import httpx
import pytest

from app.services.write_targets import FieldWrite, WriteTargetError
from app.services.write_targets.github import GitHubTarget

REPO = "acme/site"
FILE = "src/pages/about.html"
CONTENT = '<head><title>Old Title</title><img src="/cat.png"></head>'


def _b64(text):
    return base64.b64encode(text.encode()).decode()


class _Repo:
    """A tiny stand-in for the GitHub API: enough state to answer the whole
    sequence and record what was sent."""

    def __init__(self, files=None, push=True, pulls=None):
        self.files = files if files is not None else {FILE: CONTENT}
        self.push = push
        self.pulls = pulls or {}
        self.commits = []
        self.created_refs = []
        self.opened = []
        self.closed = []
        self.deleted_refs = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}

        if method == "GET" and path == f"/repos/{REPO}":
            return httpx.Response(200, json={
                "full_name": REPO, "default_branch": "main", "permissions": {"push": self.push},
            })
        if method == "GET" and path == "/search/code":
            needle = request.url.params["q"].split('"')[1]
            hits = [{"path": p} for p, text in self.files.items() if needle in text]
            return httpx.Response(200, json={"items": hits})
        if method == "GET" and path.startswith(f"/repos/{REPO}/contents/"):
            name = path.split("/contents/", 1)[1]
            if name not in self.files:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"encoding": "base64", "content": _b64(self.files[name]), "sha": f"sha-{name}"})
        if method == "GET" and path.startswith(f"/repos/{REPO}/git/ref/heads/"):
            return httpx.Response(200, json={"object": {"sha": "headsha"}})
        if method == "POST" and path == f"/repos/{REPO}/git/refs":
            self.created_refs.append(body["ref"])
            return httpx.Response(201, json={})
        if method == "PUT" and path.startswith(f"/repos/{REPO}/contents/"):
            name = path.split("/contents/", 1)[1]
            self.commits.append((name, base64.b64decode(body["content"]).decode(), body["message"]))
            return httpx.Response(200, json={})
        if method == "POST" and path == f"/repos/{REPO}/pulls":
            number = 100 + len(self.opened)
            self.opened.append(body)
            return httpx.Response(201, json={"number": number, "html_url": f"https://github.com/{REPO}/pull/{number}"})
        if method == "GET" and path.startswith(f"/repos/{REPO}/pulls/"):
            number = path.rsplit("/", 1)[1]
            return httpx.Response(200, json=self.pulls.get(number, {"state": "open", "merged": False, "html_url": "u"}))
        if method == "PATCH" and path.startswith(f"/repos/{REPO}/pulls/"):
            self.closed.append(path.rsplit("/", 1)[1])
            return httpx.Response(200, json={})
        if method == "DELETE" and path.startswith(f"/repos/{REPO}/git/refs/heads/"):
            self.deleted_refs.append(path.split("/heads/", 1)[1])
            return httpx.Response(204)
        return httpx.Response(404, json={"message": f"unhandled {method} {path}"})


def _target(repo: _Repo, branch="main"):
    target = GitHubTarget(REPO, "token", branch)
    target._client = lambda: httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(repo.handler)
    )
    return target


# --- the credential ---


def test_a_token_without_write_access_is_reported_before_anything_is_stored():
    status = _target(_Repo(push=False)).test()

    assert status.ok is False
    assert "Contents: read and write" in status.detail


def test_a_working_token_says_what_will_happen():
    """"Applied" means something different here, so the connect message says so
    rather than letting the user assume the change goes live."""
    status = _target(_Repo()).test()

    assert status.ok
    assert "pull request" in status.detail and "review and merge" in status.detail


def test_a_revoked_token_is_a_readable_failure():
    target = GitHubTarget(REPO, "token", "main")
    target._client = lambda: httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={}))
    )
    status = target.test()

    assert status.ok is False
    assert "revoked" in status.detail


# --- the happy path ---


def test_a_change_becomes_a_branch_a_commit_and_a_pull_request():
    repo = _Repo()

    receipt = _target(repo).write(
        "https://acme.test/about", [FieldWrite(field="title_tag", value="New Title", before="Old Title")]
    )

    assert repo.created_refs and repo.created_refs[0].startswith("refs/heads/signal/seo/")
    name, content, message = repo.commits[0]
    assert name == FILE and "<title>New Title</title>" in content
    assert "about" in message
    assert receipt.url == f"https://github.com/{REPO}/pull/100"
    assert "Merge it to apply" in receipt.detail


def test_the_pull_request_body_shows_the_before_and_after():
    """The pull request is where a human decides whether this is right, so it has
    to carry the same before/after the user approved."""
    repo = _Repo()
    _target(repo).write("https://acme.test/about", [FieldWrite(field="title_tag", value="New Title", before="Old Title")])

    body = repo.opened[0]["body"]
    assert "Old Title" in body and "New Title" in body
    assert FILE in body


def test_several_fields_in_one_file_become_one_pull_request():
    repo = _Repo(files={FILE: '<title>Old Title</title><link rel="canonical" href="https://acme.test/old">'})

    _target(repo).write(
        "https://acme.test/about",
        [
            FieldWrite(field="title_tag", value="New Title", before="Old Title"),
            FieldWrite(field="canonical_tag", value="https://acme.test/about", before="https://acme.test/old"),
        ],
    )

    assert len(repo.opened) == 1, "one review, not one per field"
    assert len(repo.commits) == 1
    _, content, _ = repo.commits[0]
    assert "New Title" in content and 'href="https://acme.test/about"' in content


# --- the refusals ---


def test_a_field_the_page_does_not_have_is_refused_with_what_to_do():
    """This target replaces text it can find; it does not invent a place to put a
    tag that is not there. Generating framework-specific syntax at a guessed
    position would be a mistake a pull request makes reviewable, not right."""
    with pytest.raises(WriteTargetError, match="Add the tag once by hand"):
        _target(_Repo()).write(
            "https://acme.test/about", [FieldWrite(field="meta_description", value="A description", before=None)]
        )


def test_text_that_appears_twice_in_a_file_is_refused():
    repo = _Repo(files={FILE: "<title>Old Title</title><!-- Old Title again -->"})

    with pytest.raises(WriteTargetError, match="more than once"):
        _target(repo).write(
            "https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")]
        )


def test_text_in_several_files_is_refused():
    repo = _Repo(files={FILE: CONTENT, "src/pages/other.html": CONTENT})

    with pytest.raises(WriteTargetError, match="will not guess which one"):
        _target(repo).write(
            "https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")]
        )


def test_a_value_generated_at_build_time_is_explained_not_silently_skipped():
    repo = _Repo(files={FILE: "nothing relevant here"})

    with pytest.raises(WriteTargetError, match="generated"):
        _target(repo).write(
            "https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")]
        )


# --- alt text, the one field that needs no existing value ---


def test_alt_text_is_added_using_the_src_as_the_anchor():
    repo = _Repo()

    _target(repo).write(
        "https://acme.test/about",
        [FieldWrite(field="image_alt_text", value="A ginger cat", subject="/cat.png", before=None)],
    )

    _, content, _ = repo.commits[0]
    assert '<img src="/cat.png" alt="A ginger cat">' in content


def test_alt_text_in_markdown_keeps_the_link_intact():
    repo = _Repo(files={"content/about.md": "text ![](/cat.png) more"})

    _target(repo).write(
        "https://acme.test/about",
        [FieldWrite(field="image_alt_text", value="A ginger cat", subject="/cat.png", before=None)],
    )

    _, content, _ = repo.commits[0]
    assert content == "text ![A ginger cat](/cat.png) more"


# --- undo ---


def test_reverting_an_unmerged_change_closes_the_pull_request():
    repo = _Repo(pulls={"100": {"state": "open", "merged": False, "html_url": "u"}})

    receipt = _target(repo).revert(
        "https://acme.test/about",
        [FieldWrite(field="title_tag", value="Old Title", before="New Title")],
        {"ref": "100", "extra": {"branch": "signal/seo/x", "base": "main"}},
    )

    assert repo.closed == ["100"]
    assert repo.deleted_refs == ["signal/seo/x"]
    assert not repo.opened, "nothing reached main, so nothing needs reversing"
    assert "Closed pull request #100" in receipt.detail


def test_reverting_a_merged_change_opens_a_second_pull_request():
    """Nothing is force-pushed and no history is rewritten - the way back out of a
    merged commit is another reviewable change."""
    repo = _Repo(
        files={FILE: "<title>New Title</title>"},
        pulls={"100": {"state": "closed", "merged": True, "html_url": "u"}},
    )

    receipt = _target(repo).revert(
        "https://acme.test/about",
        [FieldWrite(field="title_tag", value="Old Title", before="New Title")],
        {"ref": "100", "extra": {"branch": "signal/seo/x", "base": "main"}},
    )

    assert repo.closed == []
    assert len(repo.opened) == 1
    _, content, _ = repo.commits[0]
    assert "<title>Old Title</title>" in content
    assert "already merged" in receipt.detail


def test_an_already_closed_pull_request_is_not_closed_twice():
    repo = _Repo(pulls={"100": {"state": "closed", "merged": False, "html_url": "u"}})

    receipt = _target(repo).revert(
        "https://acme.test/about", [FieldWrite(field="title_tag", value="Old", before="New")], {"ref": "100"}
    )

    assert repo.closed == []
    assert "already closed" in receipt.detail
