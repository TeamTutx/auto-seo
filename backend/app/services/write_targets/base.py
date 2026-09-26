"""The contract every place a site's content can live implements.

Same shape as app/services/ai_providers and rank_providers - one interface,
several implementations - with one deliberate difference: the choice is per
**site**, not per config value. An AI vendor is an operator's decision that
applies to everything; where a site's content lives is a fact about that site,
and two sites in one account routinely differ.

Three things every implementation has to be honest about:

- **`supports`** - the fields it can genuinely write. A WordPress without an SEO
  plugin exposing its REST fields cannot set a meta description, and a target
  that claims otherwise produces a button that fails. The router refuses an
  unsupported field instead, and the UI shows the copy-it-yourself path.
- **`writes_immediately`** - True for a CMS (the change is live when the call
  returns), False for a repository (it is a pull request, and a human merges
  it). The difference is user-visible: "applied" means something different, and
  so does undo.
- **`revert`** - every implementation has one. A write with no way back is not
  shippable, so this is part of the interface rather than an optional extra.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence


class WriteTargetError(Exception):
    """The target could not do what was asked, for a reason worth showing the
    user - a bad credential, a page it cannot find, an ambiguous match. Carries
    a sentence written for whoever clicked the button, not a stack trace."""


@dataclass
class Receipt:
    """What a write produced, kept so it can be undone and pointed at.

    `ref` is the machine handle (a WordPress post id, a pull request number) and
    is what revert needs. `url` is for the user - the edit screen, or the PR."""
    ref: str
    url: Optional[str] = None
    detail: str = ""
    extra: Dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ref": self.ref, "url": self.url, "detail": self.detail, **({"extra": self.extra} if self.extra else {})}


@dataclass
class FieldWrite:
    """One field to set. Decoupled from the ProposedChange row so a target can
    be tested without a database, and so `revert` can pass `before` as the new
    value without inventing a fake row."""
    field: str
    value: str
    subject: str = ""  # the image src, for image_alt_text
    before: Optional[str] = None


class WriteTarget(ABC):
    kind: str
    writes_immediately: bool = True

    #: Fields this target can set. A subclass may narrow it per instance (see
    #: WordPress, where it depends on what a connect-time probe found).
    supports: Sequence[str] = ()

    def can_write(self, field_name: str) -> bool:
        return field_name in self.supports

    @abstractmethod
    def test(self) -> "TargetStatus":
        """Check the credential and report what was found, without writing
        anything. Never raises for an expected failure - a wrong password is a
        normal outcome the user needs to read, not an exception."""

    @abstractmethod
    def write(self, page_url: str, writes: List[FieldWrite]) -> Receipt:
        """Set every field in `writes` on the page at `page_url`, as one unit
        where the target allows it (one commit and one pull request; one
        WordPress update call). Raises WriteTargetError with a readable reason."""

    @abstractmethod
    def revert(self, page_url: str, writes: List[FieldWrite], receipt: Optional[dict]) -> Receipt:
        """Put back what was there. `writes` carry the original values as
        `value`; `receipt` is what the matching write returned."""


@dataclass
class TargetStatus:
    ok: bool
    detail: str
    #: What the probe found this target can write, when that is discoverable
    #: (WordPress). None = "whatever the class says it supports".
    capabilities: Optional[List[str]] = None
