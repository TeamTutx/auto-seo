"""The GitHub write path.

Driven by httpx.MockTransport: no repository is touched and no pull request is
opened. What these prove is the sequence (search, read, branch, commit, pull
request) and, more importantly, that every case where Signal cannot be certain
which text to change is a refusal rather than a guess - because the failure mode
is editing the wrong file in somebody's codebase.
"""
import base64
import io
import json
import tarfile
import time

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

    def _tarball(self) -> bytes:
        """What GitHub's tarball endpoint returns: a gzipped tar whose members
        all sit under a <owner>-<repo>-<sha>/ directory."""
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as archive:
            for name, text in self.files.items():
                raw = text.encode()
                info = tarfile.TarInfo(name=f"acme-site-abc1234/{name}")
                info.size = len(raw)
                info.mtime = int(time.time())
                archive.addfile(info, io.BytesIO(raw))
        return buf.getvalue()

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method
        body = json.loads(request.content) if request.content else {}

        if method == "GET" and path == f"/repos/{REPO}":
            return httpx.Response(200, json={
                "full_name": REPO, "default_branch": "main", "permissions": {"push": self.push},
            })
        if method == "GET" and path == f"/repos/{REPO}/tarball/main":
            return httpx.Response(200, content=self._tarball(), headers={"Content-Type": "application/gzip"})
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
    assert FILE in receipt.detail, "the receipt names the file, since a source edit can reach further than one page"
    assert "shared by more than one page" in receipt.detail


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


def test_a_missing_tag_with_nothing_to_locate_the_page_by_is_refused():
    """A tag that is not on the page anchors on nothing, so the file is found by
    something else the page shows. With no anchors at all - a page whose title,
    description and heading are all empty or all absent from the tree - there is
    no evidence to choose a file from, and choosing one anyway is how you edit a
    stranger's wrong file."""
    with pytest.raises(WriteTargetError, match="Add the tag once by hand"):
        _target(_Repo()).write(
            "https://acme.test/about", [FieldWrite(field="meta_description", value="A description", before=None)]
        )


def test_a_missing_canonical_is_added_using_the_title_as_the_anchor():
    """The case that made this exist: quickfitcv.com had no canonical tag on any
    page, so every fix for one was refused and the audit stayed red with nothing
    the owner could press."""
    repo = _Repo()

    _target(repo).write(
        "https://acme.test/about",
        [FieldWrite(
            field="canonical_tag", value="https://acme.test/about", before=None, anchors=["Old Title"],
        )],
    )

    name, content, message = repo.commits[0]
    assert name == FILE
    assert '<link rel="canonical" href="https://acme.test/about">' in content
    assert "<title>Old Title</title>" in content, "the anchor is read, never rewritten"
    assert "set canonical tag" in message


def test_the_page_half_of_a_templated_title_is_tried_when_the_whole_is_in_no_file():
    """`title: { template: "%s \u00b7 Acme" }` means the live <title> exists in no
    file. Searching for the whole of it finds nothing, which is not the same as
    the page being unfindable - the half that belongs to the page is right there."""
    repo = _Repo(files={
        "app/layout.tsx": 'export const metadata = { title: { template: "%s \u00b7 Acme" } };\n',
        "app/login/page.tsx": 'export const metadata: Metadata = { title: "Sign in" };\n',
    })

    _target(repo).write(
        "https://acme.test/login/",
        [FieldWrite(
            field="canonical_tag",
            value="https://acme.test/login/",
            before=None,
            anchors=["Sign in \u00b7 Acme", "Sign in"],
        )],
    )

    name, content, _ = repo.commits[0]
    assert name == "app/login/page.tsx", "not the layout, which holds the other half"
    assert 'alternates: { canonical: "https://acme.test/login/" }' in content


def test_a_tag_is_not_inserted_into_the_layout_that_happens_to_hold_the_title():
    """The anchor can perfectly well land in a shared layout - Signal's own title
    is root metadata shared by fourteen pages. Replacing a string there is bad
    and shows up in the diff; adding a canonical tag there tells Google all
    fourteen are the same page, and looks like three harmless added lines."""
    repo = _Repo(files={"app/layout.tsx": "<head><title>Acme</title></head>"})

    with pytest.raises(WriteTargetError, match="shared layout"):
        _target(repo).write(
            "https://acme.test/",
            [FieldWrite(field="canonical_tag", value="https://acme.test/", before=None, anchors=["Acme"])],
        )

    assert not repo.created_refs and not repo.opened, "refused before anything was created"


def test_a_tag_is_not_inserted_into_a_component_that_shares_the_pages_words():
    repo = _Repo(files={"components/auth-form.tsx": "export function AuthForm() {\n  return <button>Sign in</button>;\n}\n"})

    with pytest.raises(WriteTargetError, match="does not decide the page's <head>"):
        _target(repo).write(
            "https://acme.test/login/",
            [FieldWrite(field="canonical_tag", value="https://acme.test/login/", before=None, anchors=["Sign in"])],
        )


def test_an_added_tag_and_a_changed_one_travel_in_one_pull_request():
    repo = _Repo()

    _target(repo).write(
        "https://acme.test/about",
        [
            FieldWrite(field="title_tag", value="New Title", before="Old Title"),
            FieldWrite(
                field="canonical_tag", value="https://acme.test/about", before=None, anchors=["Old Title"],
            ),
        ],
    )

    assert len(repo.opened) == 1 and len(repo.commits) == 1, "one review, not one per field"
    _, content, _ = repo.commits[0]
    assert "<title>New Title</title>" in content
    assert '<link rel="canonical" href="https://acme.test/about">' in content


def test_the_pull_request_separates_new_tags_from_edited_ones():
    """A reviewer checks a different thing for each. An edit is "is this value
    better"; an addition is "is this the right file for this page", because that
    one Signal chose rather than was told."""
    repo = _Repo()

    _target(repo).write(
        "https://acme.test/about",
        [FieldWrite(
            field="canonical_tag", value="https://acme.test/about", before=None, anchors=["Old Title"],
        )],
    )

    body = repo.opened[0]["body"]
    assert "canonical tag (added)" in body
    assert "_(not set)_" in body
    assert "new tags, not edits" in body
    assert "the file is the right page" in body


def test_undoing_a_merged_addition_is_handed_back_rather_than_guessed_at():
    """Reverting an edit writes the old value back. Reverting an addition would
    mean deleting lines Signal wrote, which is a different act on somebody's
    repository - and the merge commit is already the exact record of what to
    undo, so there is a better answer than a half-right automatic one."""
    repo = _Repo(
        files={FILE: '<head><title>T</title><link rel="canonical" href="https://acme.test/about"></head>'},
        pulls={"100": {"state": "closed", "merged": True, "html_url": "u"}},
    )

    with pytest.raises(WriteTargetError, match="deleting lines"):
        _target(repo).revert(
            "https://acme.test/about",
            [FieldWrite(field="canonical_tag", value="", before="https://acme.test/about")],
            {"ref": "100", "extra": {"branch": "signal/seo/x", "base": "main"}},
        )

    assert not repo.opened, "no second pull request that blanks the href"


def test_undoing_an_unmerged_addition_still_just_closes_the_pull_request():
    """Nothing reached the branch, so there is nothing to delete and the clean
    undo already exists."""
    repo = _Repo(pulls={"100": {"state": "open", "merged": False, "html_url": "u"}})

    receipt = _target(repo).revert(
        "https://acme.test/about",
        [FieldWrite(field="canonical_tag", value="", before="https://acme.test/about")],
        {"ref": "100", "extra": {"branch": "signal/seo/x", "base": "main"}},
    )

    assert repo.closed == ["100"]
    assert "Closed pull request #100" in receipt.detail


def test_text_that_appears_twice_in_a_file_is_refused():
    repo = _Repo(files={FILE: "<title>Old Title</title><!-- Old Title again -->"})

    with pytest.raises(WriteTargetError, match="appears 2 times"):
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

    with pytest.raises(WriteTargetError, match="assembled at build time"):
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


def test_the_pull_request_warns_that_a_shared_string_moves_every_page_using_it():
    """Found by pointing this at a real repository: signal-seo.in's own title
    lives in the root layout, so "fix the home page title" would have retitled
    fourteen pages. Nothing in the value says whether it is page-specific, so the
    pull request says so and the human merging it decides."""
    repo = _Repo()
    _target(repo).write("https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    body = repo.opened[0]["body"]
    assert "shared layout" in body and "override" in body


def test_a_value_with_punctuation_is_found_where_code_search_missed_it():
    """The regression that sent this from code search to the tarball. GitHub's
    code search tokenises, so a title carrying an em dash and two commas matched
    nothing while sitting in the repository the whole time. Substring matching
    over the real tree has no query language to lose it in.

    Deliberately not Signal's own title. A test quoting the live string becomes a
    second match the moment Signal is pointed at this very repository - which is
    exactly what happened, and is the tie the tests below cover breaking."""
    title = "Acme — Widgets, Gadgets and Gizmos"
    repo = _Repo(files={"frontend/app/layout.tsx": f'  title: "{title}",\n'})

    _target(repo).write("https://acme.test/", [FieldWrite(field="title_tag", value="New Title", before=title)])

    name, content, _ = repo.commits[0]
    assert name == "frontend/app/layout.tsx"
    assert 'title: "New Title",' in content


def test_a_binary_file_in_the_repo_does_not_break_the_search():
    repo = _Repo(files={FILE: CONTENT})
    original_tarball = repo._tarball

    def with_binary():
        import io as _io, tarfile as _tar, time as _time
        buf = _io.BytesIO()
        with _tar.open(fileobj=buf, mode="w:gz") as archive:
            for name, blob in [(FILE, CONTENT.encode()), ("logo.png", b"\x89PNG\r\n\x1a\n\xff\xfe")]:
                info = _tar.TarInfo(name=f"acme-site-abc1234/{name}")
                info.size = len(blob)
                info.mtime = int(_time.time())
                archive.addfile(info, _io.BytesIO(blob))
        return buf.getvalue()

    repo._tarball = with_binary
    _target(repo).write("https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    assert repo.commits[0][0] == FILE


# --- telling a source apart from something that merely quotes it ---


def test_a_test_file_holding_the_same_string_does_not_block_the_real_one():
    """Found by pointing Signal at its own repository: the regression test above
    quoted the live title, so the scan matched two files and refused to guess.
    A file under tests/ does not serve a web page."""
    repo = _Repo(files={
        "frontend/app/layout.tsx": '  title: "Old Title",\n',
        "backend/tests/test_write_target_github.py": 'assert title == "Old Title"\n',
    })

    _target(repo).write("https://acme.test/", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    assert repo.commits[0][0] == "frontend/app/layout.tsx"
    assert len(repo.commits) == 1


@pytest.mark.parametrize("noise_path", [
    "frontend/out/index.html",
    "node_modules/pkg/readme.js",
    "dist/bundle.min.js",
    "src/__tests__/layout.spec.tsx",
    "app/layout.test.tsx",
])
def test_build_output_and_vendored_code_are_discounted_too(noise_path):
    repo = _Repo(files={
        "frontend/app/layout.tsx": '  title: "Old Title",\n',
        noise_path: "<title>Old Title</title>",
    })

    _target(repo).write("https://acme.test/", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    assert repo.commits[0][0] == "frontend/app/layout.tsx"


def test_markdown_content_is_never_discounted():
    """A Hugo or Jekyll site's pages *are* markdown, so treating .md as noise
    would make this useless for a whole category of site."""
    repo = _Repo(files={"content/about.md": "# Old Title\n"})

    _target(repo).write("https://acme.test/about", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    assert repo.commits[0][0] == "content/about.md"


def test_a_match_only_in_a_test_file_is_still_reported():
    """The discount breaks ties; it never hides the only match there is. Saying
    "not found" for a value plainly in the repository would send someone hunting
    for a problem that does not exist."""
    repo = _Repo(files={"backend/tests/test_pages.py": 'assert title == "Old Title"\n'})

    _target(repo).write("https://acme.test/", [FieldWrite(field="title_tag", value="New", before="Old Title")])

    assert repo.commits[0][0] == "backend/tests/test_pages.py"


def test_two_real_sources_are_still_a_refusal():
    repo = _Repo(files={
        "frontend/app/layout.tsx": '  title: "Old Title",\n',
        "frontend/app/other/layout.tsx": '  title: "Old Title",\n',
    })

    with pytest.raises(WriteTargetError, match="all look like sources"):
        _target(repo).write("https://acme.test/", [FieldWrite(field="title_tag", value="New", before="Old Title")])


# --- the repository running ahead of the deployed site ---


def test_a_merged_pull_request_not_yet_deployed_is_named_as_the_cause():
    """The failure that looked like "this value is generated at build time".

    Between merging a pull request and the site finishing its rebuild, the
    repository holds the new value while the live page still serves the old one.
    A fix written from that page therefore looks for a string the repository no
    longer has - and the staleness check cannot see it, because the live page it
    compares against is exactly the stale thing. A value Signal itself wrote
    sitting in the tree is what tells the two apart."""
    repo = _Repo(files={FILE: '<title>What the merged PR set</title>'})

    with pytest.raises(WriteTargetError, match="has not rebuilt"):
        _target(repo).write(
            "https://acme.test/about",
            [FieldWrite(
                field="title_tag",
                value="A third title",
                before="Old Title",
                previously_wrote=["What the merged PR set"],
            )],
        )


def test_a_value_genuinely_absent_still_says_so():
    """The other cause of the same symptom keeps its own message: nothing Signal
    wrote is in the tree either, so this really is assembled at build time."""
    repo = _Repo(files={FILE: "nothing relevant here"})

    with pytest.raises(WriteTargetError, match="assembled at build time"):
        _target(repo).write(
            "https://acme.test/about",
            [FieldWrite(
                field="title_tag",
                value="New",
                before="Old Title",
                previously_wrote=["Something Signal wrote that is also absent"],
            )],
        )


def test_an_unmerged_pull_request_does_not_trigger_the_drift_message():
    """An open pull request has changed nothing yet, so the repository still has
    the original value and the write should simply work. Treating this as drift
    would refuse every second fix until the first was merged."""
    repo = _Repo(files={FILE: CONTENT})

    _target(repo).write(
        "https://acme.test/about",
        [FieldWrite(
            field="title_tag",
            value="Another title",
            before="Old Title",
            previously_wrote=["A title from a pull request nobody merged"],
        )],
    )

    assert repo.commits[0][0] == FILE


def test_a_layout_found_by_an_inherited_description_does_not_stop_the_search():
    """A page with no description of its own serves the layout's, so searching
    for what is on the page finds the layout - which may not have a tag added to
    it. That is a reason to try the page's own title next, not to refuse: the
    first version stopped here and could not add a canonical to any page whose
    description came from the layout, which was most of them."""
    repo = _Repo(files={
        "app/layout.tsx": (
            'export const metadata: Metadata = {\n'
            '  description: "Tailor your resume to every job.",\n'
            '};\n'
        ),
        "app/login/page.tsx": 'export const metadata: Metadata = { title: "Sign in" };\n',
    })

    _target(repo).write(
        "https://acme.test/login/",
        [FieldWrite(
            field="canonical_tag",
            value="https://acme.test/login/",
            before=None,
            # What the live page shows: a templated title, then the description
            # it inherited, then the page's own half of the title.
            anchors=["Sign in · Acme", "Tailor your resume to every job.", "Sign in"],
        )],
    )

    name, content, _ = repo.commits[0]
    assert name == "app/login/page.tsx"
    assert 'alternates: { canonical: "https://acme.test/login/" }' in content


def test_files_that_could_not_own_a_head_do_not_make_the_anchor_ambiguous():
    """"Privacy policy" is in the privacy page, a changelog and an app-store
    listing. Judging ambiguity before asking which files could even receive the
    tag refused the one real answer in the name of two that were never
    candidates - which is how four of five pages on the first real site came
    back as "add it by hand"."""
    repo = _Repo(files={
        "plan.md": "- [x] Privacy policy page\n",
        "store/LISTING.md": "Privacy policy: https://acme.test/privacy/\n",
        "app/privacy/page.tsx": (
            'export const metadata: Metadata = { title: "Privacy policy" };\n'
            "\n"
            "export default function PrivacyPage() {\n"
            '  return <LegalPage title="Privacy policy">text</LegalPage>;\n'
            "}\n"
        ),
    })

    _target(repo).write(
        "https://acme.test/privacy/",
        [FieldWrite(
            field="canonical_tag", value="https://acme.test/privacy/", before=None,
            anchors=["Privacy policy · Acme", "Privacy policy"],
        )],
    )

    name, content, _ = repo.commits[0]
    assert name == "app/privacy/page.tsx"
    assert 'alternates: { canonical: "https://acme.test/privacy/" }' in content


def test_an_anchor_appearing_twice_in_one_file_still_identifies_it():
    """Replacing needs to know which occurrence; adding only needs to know which
    file, and twice in one file is stronger evidence of that, not weaker."""
    repo = _Repo(files={"app/terms/page.tsx": (
        'export const metadata: Metadata = { title: "Terms of service" };\n'
        "\n"
        "export default function TermsPage() {\n"
        '  return <LegalPage title="Terms of service">text</LegalPage>;\n'
        "}\n"
    )})

    _target(repo).write(
        "https://acme.test/terms/",
        [FieldWrite(field="canonical_tag", value="https://acme.test/terms/", before=None, anchors=["Terms of service"])],
    )

    assert 'canonical: "https://acme.test/terms/"' in repo.commits[0][1]


def test_a_merged_addition_that_has_not_deployed_blames_the_deploy_not_the_file():
    """Between a merged pull request and the site's rebuild, the repository has
    the tag and the page does not - so Signal proposes adding it again. Without
    this it finds the tag already in the metadata object and reports that the
    file and the page disagree, which blames the repository for being correct."""
    repo = _Repo(files={"app/about/page.tsx": (
        'export const metadata: Metadata = {\n'
        '  title: "About us",\n'
        '  alternates: { canonical: "https://acme.test/about/" },\n'
        "};\n"
    )})

    with pytest.raises(WriteTargetError, match="has not rebuilt since that pull request was merged"):
        _target(repo).write(
            "https://acme.test/about/",
            [FieldWrite(
                field="canonical_tag",
                value="https://acme.test/about/",
                before=None,
                anchors=["About us"],
                previously_wrote=["https://acme.test/about/"],
            )],
        )


def test_the_urls_own_segment_breaks_a_tie_between_two_real_candidates():
    """"Sign in" labels a button on the privacy page as well as titling the
    login page, so both files could own a head and both match. Refusing is the
    alternative, and among genuine candidates the file whose path carries the
    URL's last segment is the answer on every generator Signal meets."""
    page = 'export const metadata: Metadata = { title: "Sign in" };\n'
    repo = _Repo(files={
        "app/login/page.tsx": page,
        "app/privacy/page.tsx": 'export const metadata: Metadata = { title: "Privacy" };\n// Sign in to see it\n',
    })

    _target(repo).write(
        "https://acme.test/login/",
        [FieldWrite(field="canonical_tag", value="https://acme.test/login/", before=None, anchors=["Sign in"])],
    )

    name, content, _ = repo.commits[0]
    assert name == "app/login/page.tsx"
    assert 'canonical: "https://acme.test/login/"' in content


def test_the_segment_tie_break_does_not_pick_when_it_matches_nothing():
    """It narrows to one or it stands aside - it never ranks."""
    page = 'export const metadata: Metadata = { title: "Sign in" };\n'
    repo = _Repo(files={"app/a/page.tsx": page, "app/b/page.tsx": page})

    with pytest.raises(WriteTargetError, match="will not guess which one is this page"):
        _target(repo).write(
            "https://acme.test/login/",
            [FieldWrite(field="canonical_tag", value="https://acme.test/login/", before=None, anchors=["Sign in"])],
        )
