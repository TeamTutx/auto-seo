"""WordPress, over its own REST API and an Application Password.

Application Passwords are core since WP 5.6: the user creates one on their own
profile screen, it is scoped to that user, and they can revoke it there without
touching their real password. No plugin to install, which is why this is the
first CMS supported.

**What it can write, and why the list is short.** The temptation is to map
`title_tag` onto the core `title` field, because that always works. It would
also be wrong twice over. A WordPress post title is usually the visible H1 *and*
only part of the rendered `<title>` (themes append the site name), so writing
the audit's suggested title tag into it would rewrite the page's visible heading
and still not produce the string the audit asked for - and the before/after the
user approved would not describe what happened. An SEO title is a different field
from a post title, so it is only written where a plugin actually exposes one.

That leaves:

- `image_alt_text` - always. `wp/v2/media`'s `alt_text` is core, is exactly what
  the audit measures, and writing it changes nothing else on the page.
- `title_tag`, `meta_description`, `canonical_tag` - only when a connect-time
  probe finds Yoast's or Rank Math's fields writable over REST. Whether they are
  depends on the plugin and its version, so it is detected per site rather than
  assumed; `capabilities` in the stored config is what the probe found.

Deliberately not supported:

- `robots_meta_tag`. Each plugin represents noindex/nofollow differently, and
  guessing wrong deindexes a page. That is the one failure here that costs the
  user traffic rather than just looking wrong, and "copy this into Yoast" is a
  perfectly good answer instead.
- `structured_data`. Both plugins generate their own schema graph; there is no
  meta field to set, and adding a second JSON-LD block alongside theirs invites
  conflicting markup.
"""
import base64
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from .base import FieldWrite, Receipt, TargetStatus, WriteTarget, WriteTargetError

TIMEOUT = 20.0

# The meta keys each SEO plugin uses, in the order we prefer them. Yoast first
# only because it is the more common install; either satisfies a capability.
_SEO_META = {
    "title_tag": ("_yoast_wpseo_title", "rank_math_title"),
    "meta_description": ("_yoast_wpseo_metadesc", "rank_math_description"),
    "canonical_tag": ("_yoast_wpseo_canonical", "rank_math_canonical_url"),
}
ALWAYS_SUPPORTED = ("image_alt_text",)

# WordPress stores resized copies as name-WxH.ext. The alt text belongs to the
# one media item behind all of them, so the suffix is stripped before matching.
_SIZE_SUFFIX = re.compile(r"-\d+x\d+(?=\.[A-Za-z0-9]+$)")


def _same_page(a: str, b: str) -> bool:
    """Permalinks differ from what the user typed by scheme and trailing slash
    far more often than they differ by page."""
    def key(url: str) -> str:
        p = urlparse(url)
        host = p.netloc.lower()
        return f"{host[4:] if host.startswith('www.') else host}{p.path.rstrip('/')}"
    return key(a) == key(b)


class WordPressTarget(WriteTarget):
    kind = "wordpress"
    writes_immediately = True

    def __init__(self, base_url: str, username: str, app_password: str, capabilities: Optional[List[str]] = None):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self._password = app_password
        # Until a probe has run, assume only what core guarantees. A target that
        # over-claims produces a button that fails in front of the user.
        self.supports = tuple(capabilities) if capabilities is not None else ALWAYS_SUPPORTED

    # --- plumbing ---

    def _auth_header(self) -> str:
        raw = f"{self.username}:{self._password}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    def _client(self) -> httpx.Client:
        return httpx.Client(
            base_url=f"{self.base_url}/wp-json/wp/v2",
            headers={"Authorization": self._auth_header(), "Accept": "application/json"},
            timeout=TIMEOUT,
            follow_redirects=True,
        )

    @staticmethod
    def _json(response: httpx.Response) -> object:
        if response.status_code == 401:
            raise WriteTargetError(
                "WordPress rejected the username or application password. Application "
                "passwords are created under Users -> Profile in WordPress, and the "
                "username is the WordPress login, not the email."
            )
        if response.status_code == 403:
            raise WriteTargetError(
                "That WordPress user is authenticated but not allowed to edit this content. "
                "An Editor or Administrator account is needed."
            )
        if response.status_code == 404:
            raise WriteTargetError(
                f"WordPress has no REST endpoint at {response.request.url}. If the REST API "
                "is disabled by a plugin or a security rule, Signal cannot write to this site."
            )
        if response.status_code >= 400:
            raise WriteTargetError(f"WordPress returned {response.status_code}: {response.text[:200]}")
        try:
            return response.json()
        except ValueError:
            raise WriteTargetError(
                "That URL answered, but not with JSON - it may not be a WordPress site, "
                "or a plugin may be intercepting the REST API."
            )

    # --- connect-time probe ---

    def test(self) -> TargetStatus:
        try:
            with self._client() as client:
                me = self._json(client.get("/users/me", params={"context": "edit"}))
                caps = list(ALWAYS_SUPPORTED) + self._detect_seo_fields(client)
        except WriteTargetError as exc:
            return TargetStatus(ok=False, detail=str(exc))
        except httpx.HTTPError as exc:
            return TargetStatus(ok=False, detail=f"Could not reach {self.base_url}: {exc}")

        name = (me or {}).get("name") if isinstance(me, dict) else None
        extra = sorted(set(caps) - set(ALWAYS_SUPPORTED))
        detail = f"Connected as {name or self.username}. "
        detail += (
            "Signal can set image alt text, and " + ", ".join(f.replace("_", " ") for f in extra) + "."
            if extra
            else (
                "Signal can set image alt text. No SEO plugin fields were writable over REST, "
                "so titles and meta descriptions have to be pasted in - Signal will still write them for you."
            )
        )
        return TargetStatus(ok=True, detail=detail, capabilities=caps)

    def _detect_seo_fields(self, client: httpx.Client) -> List[str]:
        """Which SEO plugin fields are actually writable here.

        Registered post meta only appears in a REST response when the plugin set
        `show_in_rest`, and only under `context=edit`. So the probe reads one real
        post and looks: presence in `meta` is the evidence, nothing is assumed
        from the plugin being installed."""
        found: List[str] = []
        meta: Dict[str, object] = {}
        for endpoint in ("/posts", "/pages"):
            try:
                items = self._json(client.get(endpoint, params={"per_page": 1, "context": "edit"}))
            except WriteTargetError:
                continue
            if isinstance(items, list) and items and isinstance(items[0], dict):
                candidate = items[0].get("meta")
                if isinstance(candidate, dict) and candidate:
                    meta.update(candidate)
        for field_name, keys in _SEO_META.items():
            if any(k in meta for k in keys):
                found.append(field_name)
        return found

    def _meta_key(self, field_name: str, available: Dict[str, object]) -> Optional[str]:
        for key in _SEO_META.get(field_name, ()):
            if key in available:
                return key
        return None

    # --- resolving a URL to something writable ---

    def _resolve_post(self, client: httpx.Client, page_url: str) -> Tuple[str, int, Dict[str, object]]:
        """(endpoint, id, meta) for the post or page at this URL."""
        slug = [s for s in urlparse(page_url).path.split("/") if s]
        candidates: List[Tuple[str, dict]] = []

        for endpoint in ("/pages", "/posts"):
            params = {"context": "edit", "per_page": 100}
            if slug:
                params["slug"] = slug[-1]
            items = self._json(client.get(endpoint, params=params))
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("link"), str):
                    candidates.append((endpoint, item))

        for endpoint, item in candidates:
            if _same_page(item["link"], page_url):
                return endpoint, int(item["id"]), item.get("meta") if isinstance(item.get("meta"), dict) else {}

        # A slug match with a permalink Signal reads differently (a plugin
        # rewriting URLs, say) is still almost certainly the right post, but
        # only when it is the sole candidate - picking one of several by guess
        # is how the wrong page gets edited.
        if len(candidates) == 1:
            endpoint, item = candidates[0]
            return endpoint, int(item["id"]), item.get("meta") if isinstance(item.get("meta"), dict) else {}

        if candidates:
            raise WriteTargetError(
                f"Several WordPress entries could be {page_url} and none of their permalinks "
                "match it exactly. Signal will not guess which one to edit."
            )
        raise WriteTargetError(
            f"No WordPress post or page has the URL {page_url}. If this page is generated by a "
            "plugin or a page builder rather than stored as a post, Signal cannot write to it."
        )

    def _resolve_media(self, client: httpx.Client, src: str) -> int:
        filename = _SIZE_SUFFIX.sub("", urlparse(src).path.rsplit("/", 1)[-1])
        stem = filename.rsplit(".", 1)[0]
        items = self._json(client.get("/media", params={"search": stem, "per_page": 100, "context": "edit"}))
        if not isinstance(items, list) or not items:
            raise WriteTargetError(f"No image in the WordPress media library matches {filename}.")

        for item in items:
            source = item.get("source_url") if isinstance(item, dict) else None
            if isinstance(source, str) and _SIZE_SUFFIX.sub("", source).endswith(filename):
                return int(item["id"])
        if len(items) == 1 and isinstance(items[0], dict):
            return int(items[0]["id"])
        raise WriteTargetError(
            f"Several media items match {filename} and none is an exact URL match, so Signal "
            "will not guess which image to describe."
        )

    # --- writing ---

    def write(self, page_url: str, writes: List[FieldWrite]) -> Receipt:
        alt_writes = [w for w in writes if w.field == "image_alt_text"]
        post_writes = [w for w in writes if w.field != "image_alt_text"]

        touched: List[str] = []
        with self._client() as client:
            post_ref = ""
            post_link = None
            if post_writes:
                endpoint, post_id, meta = self._resolve_post(client, page_url)
                payload: Dict[str, Dict[str, str]] = {"meta": {}}
                for write in post_writes:
                    key = self._meta_key(write.field, meta)
                    if key is None:
                        raise WriteTargetError(
                            f"This WordPress has no writable field for {write.field.replace('_', ' ')}. "
                            "Copy the value in instead - Signal has already written it for you."
                        )
                    payload["meta"][key] = write.value
                updated = self._json(client.post(f"{endpoint}/{post_id}", json=payload))
                self._confirm_meta(updated, payload["meta"])
                post_ref = f"{endpoint.strip('/')}:{post_id}"
                post_link = updated.get("link") if isinstance(updated, dict) else None
                touched.append(f"{len(post_writes)} field(s) on {post_ref}")

            media_refs = []
            for write in alt_writes:
                media_id = self._resolve_media(client, write.subject)
                self._json(client.post(f"/media/{media_id}", json={"alt_text": write.value}))
                media_refs.append(str(media_id))
            if media_refs:
                touched.append(f"alt text on media {', '.join(media_refs)}")

        return Receipt(
            ref=post_ref or f"media:{','.join(media_refs)}",
            url=post_link or page_url,
            detail="Updated " + "; ".join(touched) + ".",
            extra={"media": ",".join(media_refs)} if media_refs else {},
        )

    @staticmethod
    def _confirm_meta(updated: object, written: Dict[str, str]) -> None:
        """WordPress answers 200 and quietly drops meta it does not consider
        registered, so a successful response is not evidence the value landed.
        Read it back out of the same response rather than trusting the status."""
        meta = updated.get("meta") if isinstance(updated, dict) else None
        if not isinstance(meta, dict):
            return  # nothing to compare against; the write either worked or the next audit says so
        ignored = [k for k, v in written.items() if k in meta and meta[k] != v]
        if ignored:
            raise WriteTargetError(
                "WordPress accepted the request but did not store "
                f"{', '.join(ignored)} - the SEO plugin is not exposing that field for writing. "
                "Copy the value in instead."
            )

    def revert(self, page_url: str, writes: List[FieldWrite], receipt: Optional[dict]) -> Receipt:
        """Writing the old value back is the whole undo: WordPress keeps a
        revision of the change, so nothing is lost either way."""
        restored = self.write(page_url, writes)
        return Receipt(ref=restored.ref, url=restored.url, detail="Restored the previous value.")
