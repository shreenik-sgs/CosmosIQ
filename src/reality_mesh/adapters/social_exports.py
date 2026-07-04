"""The X / Social LOCAL-EXPORT adapter (IMPLEMENTATION-014E, Phase-014 priority #9).

:class:`SocialExportsAdapter` reads OPERATOR-DOWNLOADED local X/social export files
(``data_dir/social_export_<date>.json`` -- a list of posts an operator exported by hand) and
emits ``narrative``-discipline :class:`~reality_mesh.models.RealityEvent`s ONLY, per
``SOURCE_ADAPTER_PRODUCTION_CONTRACT_013``. The 012H
:class:`~reality_mesh.sensors.social_narrative.SocialNarrativeAgent` consumes the emitted
mention / theme-mention / account-flavoured event shapes UNCHANGED.

THE STRICTEST ADAPTER (ARCHITECTURE_CONTRACT_012 §C -- X/social is weak-signal ONLY):

* **NO live X. NO API. NO scraping. NO credentials.** This adapter reads local files an
  operator downloaded; ``network_required=False`` and ``credentials_status="not_required"``.
  A live X path remains DEFERRED -- it would be the LAST onboarding stage of a future slice,
  and even then X/social stays weak-signal-only.
* **EVERY event is ``source_authority="rumor"``.** Assigned immediately, on every record,
  with no other value reachable in this module. Rumor stays rumor: nothing here can be
  promoted, corroborated, or canonical.
* **A social post can NEVER confirm a fact.** No code path in this module can stamp a
  verified claim status -- the token does not even exist here as a stampable literal
  (mirroring the 014C technique). The account behind a post colours the claim FLAVOUR only:
  an official company account -> ``company_claim`` (still rumor authority -- the account
  could be impersonated/hacked); a journalist account -> ``reported_claim``; an expert /
  unknown / anonymous account -> ``rumor``. An unrecognised ``author_type`` is treated
  conservatively as unknown (``rumor``) with a visible note -- never assumed upward.
* **Bot / promoter risk passes through VISIBLY.** A post's ``bot_risk_pct`` rides in
  ``numeric_values``; at or above :data:`PROMOTER_BOT_RISK_VISIBLE_PCT` the event carries an
  explicit promoter-risk conflict + data gap and the observed fact names the risk -- never
  silently filtered, never used to fabricate confidence.
* **Watchlist / theme SCOPE is enforced (the 014D rule).** Only posts matching a REQUESTED
  ticker or theme are emitted; an export entry for an unrequested subject is SKIPPED (it
  stays in the file for a future run that requests it). A requested ticker / theme with no
  post coverage across the export files becomes a NAMED gap -- never fabricated, never a
  silent demo fallback.

LOCAL FILES ONLY (onboarding stage 2 of contract §4). A missing directory / export file or a
malformed file / entry becomes a visible gap / ``parse_error`` NAMING it -- never a crash,
never a fabricated value. A STALE post (``posted_at`` -- falling back to the file's
``as_of`` -- older than :data:`SOCIAL_EXPORT_STALE_AFTER_HOURS` versus the injected ``now``)
is marked ``freshness_label="stale"`` (preserved, never dropped, never silently refreshed).

NO scheduler, NO broker, NO score / rank anywhere. Deterministic, stdlib-only, Python 3.9,
OFFLINE. Ids and ``raw_payload_ref``s are content-derived (sha256); ``now`` is an injected
string (no wall-clock anywhere).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from ..models import RealityEvent
from .base import (
    SourceAdapter,
    SourceAdapterDescriptor,
    SourceAdapterResult,
    deterministic_adapter_run_id,
)
# Reuse the audited 014A ISO parser -- timestamp parsing rules live in exactly one place.
from .local_market_data import _parse_iso

__all__ = [
    "SOCIAL_EXPORTS_ADAPTER_ID",
    "SOCIAL_EXPORTS_DESCRIPTOR",
    "SOCIAL_EXPORTS_DISCIPLINES",
    "SOCIAL_EXPORT_FILE_PREFIX",
    "SOCIAL_EXPORT_STALE_AFTER_HOURS",
    "SOCIAL_EXPORT_ACCOUNT_TYPES",
    "PROMOTER_BOT_RISK_VISIBLE_PCT",
    "SocialExportsAdapter",
]

SOCIAL_EXPORTS_ADAPTER_ID = "narrative.social_exports"

# The one discipline this adapter is the source for: the 012H SocialNarrativeAgent's.
SOCIAL_EXPORTS_DISCIPLINES: Tuple[str, ...] = ("narrative",)

# The operator file naming convention: one export per download.
SOCIAL_EXPORT_FILE_PREFIX = "social_export_"

# A post older than this (versus the injected ``now``) is marked stale. Social attention
# decays in hours; a two-day-old export is not a current read of the narrative tape.
SOCIAL_EXPORT_STALE_AFTER_HOURS = 48

# At or above this ``bot_risk_pct`` the promoter/bot risk is made VISIBLE on the event
# (conflict + gap + named in the observed fact) -- never silently filtered.
PROMOTER_BOT_RISK_VISIBLE_PCT = 50

# The closed set of account types an export entry may declare. Anything else (or a missing
# author_type) is treated conservatively as ``unknown`` -- never assumed upward.
SOCIAL_EXPORT_ACCOUNT_TYPES: Tuple[str, ...] = (
    "company_official", "journalist", "expert", "unknown")

# account_type -> (claim_status flavour, half_life). ONLY the flavour changes -- authority is
# rumor on every record and no mapping target is a verified/canonical status.
_ACCOUNT_CLAIM: Dict[str, Tuple[str, str]] = {
    "company_official": ("company_claim", "days"),
    "journalist": ("reported_claim", "hours"),
    "expert": ("rumor", "days"),
    "unknown": ("rumor", "hours"),
}

# account_type -> (event_type, source_id token) for a ticker-scoped post. The token lands in
# ``source_id`` so the 012H sensor classifies the account flavour exactly as it does for its
# own fixtures (company account / journalist / expert account / plain mention).
_ACCOUNT_EVENT: Dict[str, Tuple[str, str]] = {
    "company_official": ("company_account_claim", "company_account"),
    "journalist": ("journalist_account_report", "journalist"),
    "expert": ("expert_account_post", "expert_account"),
    "unknown": ("social_mention_spike", "mention"),
}

# The optional numeric context an export entry may carry (name -> unit). Every emitted
# numeric value carries its unit; a non-numeric value rejects the entry (parse_error).
_POST_NUMERIC_UNITS: Dict[str, str] = {
    "follower_count": "count",
    "bot_risk_pct": "pct",
    "mention_count": "count",
    "mention_velocity_zscore": "zscore",
    "unique_authors": "count",
}

# The adapter's frozen contract declaration (SOURCE_ADAPTER_PRODUCTION_CONTRACT_013 §1).
SOCIAL_EXPORTS_DESCRIPTOR = SourceAdapterDescriptor(
    adapter_id=SOCIAL_EXPORTS_ADAPTER_ID,
    source_name="X/social operator-downloaded local export files (NO live X, NO API, NO "
                "scraping, NO credentials)",
    source_type="social_export",
    source_authority="rumor",               # X/social: rumor, ALWAYS -- never promoted
    credential_requirements=(),             # local files: NO credential (env or otherwise)
    network_required=False,                 # LOCAL FILES ONLY -- live X stays deferred
    rate_limit_policy="not_applicable: local filesystem read, no remote quota",
    outputs=(
        "social_mention_spike",
        "theme_mention_spike",
        "company_account_claim",
        "journalist_account_report",
        "expert_account_post",
    ),
    claim_status_rules=(
        "source_authority=rumor is assigned immediately on EVERY record: an X/social post "
        "can never confirm a fact, whoever posts it -- rumor stays rumor, never verified, "
        "never canonical (ARCHITECTURE_CONTRACT_012 §C)",
        "official company account -> claim_status=company_claim (the company's own words "
        "on social, could be impersonation/hack -- still rumor authority)",
        "journalist / source account -> claim_status=reported_claim (a third party "
        "reported it; not independently verified)",
        "expert / unknown / anonymous account -> claim_status=rumor; an unrecognised "
        "author_type is treated as unknown with a visible note -- never assumed upward",
        "bot_risk_pct passes through VISIBLY in numeric_values; >= {0}% adds an explicit "
        "promoter-risk conflict + data gap -- never silently filtered".format(
            PROMOTER_BOT_RISK_VISIBLE_PCT),
        "watchlist/theme scope enforced: only posts matching a requested ticker or theme "
        "are emitted; a requested subject with no coverage is a NAMED gap",
    ),
    failure_modes=("source_unavailable", "parse_error"),
    description="Operator-downloaded local X/social export files feeding the 012H "
                "SocialNarrativeAgent (weak-signal only). Offline; no live X; no scheduler; "
                "no broker; labels not facts.",
)

_STATUS_TO_HEALTH = {
    "success": "healthy",
    "partial": "degraded",
    "failed": "failed",
    "skipped": "source_unavailable",
}


# --------------------------------------------------------------------------- #
# Small pure helpers                                                            #
# --------------------------------------------------------------------------- #
def _sha12(*parts: object) -> str:
    return hashlib.sha256(
        "|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:12]


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_").lower() or "x"


def _norm_theme(text: str) -> str:
    """Normalise a theme token for scope comparison (case / hyphen / underscore insensitive)."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def _normalise_tickers(watchlist) -> Tuple[str, ...]:
    """Strip / upper / dedupe (first-seen order); reject blank tokens."""
    raw = watchlist.split(",") if isinstance(watchlist, str) else list(watchlist or ())
    out: List[str] = []
    for token in raw:
        tk = str(token).strip().upper()
        if tk and tk not in out:
            out.append(tk)
    return tuple(out)


def _normalise_themes(themes) -> Tuple[str, ...]:
    """Strip / dedupe requested themes (first-seen order, original spelling kept)."""
    raw = themes.split(",") if isinstance(themes, str) else list(themes or ())
    out: List[str] = []
    for token in raw:
        th = str(token).strip()
        if th and th not in out:
            out.append(th)
    return tuple(out)


def _is_stale(posted_at: str, now: str) -> bool:
    """True iff ``posted_at`` is more than the stale threshold older than the injected ``now``.

    Deterministic: purely a comparison of the two injected strings -- no wall-clock. An
    absent / unparsable timestamp on either side reads False (the caller surfaces a warning
    for an unparsable timestamp -- staleness is never guessed).
    """
    posted_dt = _parse_iso(posted_at)
    now_dt = _parse_iso(now)
    if posted_dt is None or now_dt is None:
        return False
    return (now_dt - posted_dt) > _dt.timedelta(hours=SOCIAL_EXPORT_STALE_AFTER_HOURS)


def _text_of(entry: Dict[str, Any], *keys: str) -> str:
    """The first non-empty text among ``keys`` on ``entry`` (stripped; '' if none)."""
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _str_list(entry: Dict[str, Any], key: str) -> List[str]:
    """The list ``entry[key]`` as stripped non-empty strings. Raises on a non-list/blank."""
    value = entry.get(key)
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("{0} must be a list of strings".format(key))
    out: List[str] = []
    for element in value:
        if not isinstance(element, str) or not element.strip():
            raise ValueError("{0} entries must be non-empty strings".format(key))
        out.append(element.strip())
    return out


# --------------------------------------------------------------------------- #
# SocialExportsAdapter                                                          #
# --------------------------------------------------------------------------- #
class SocialExportsAdapter(SourceAdapter):
    """Operator-downloaded LOCAL X/social export files -> weak narrative RealityEvents.

    ``data_dir`` holds ``social_export_<date>.json`` files, each an operator-exported list
    of posts. Authority is ``rumor`` on every record; the account type flavours the claim
    only; bot/promoter risk stays visible; watchlist/theme scope is enforced. NO live X --
    offline by construction.
    """

    def __init__(self, data_dir: str) -> None:
        if not isinstance(data_dir, str) or data_dir.strip() == "":
            raise ValueError("SocialExportsAdapter requires a non-empty data_dir")
        self._data_dir = data_dir

    @property
    def descriptor(self) -> SourceAdapterDescriptor:
        return SOCIAL_EXPORTS_DESCRIPTOR

    @property
    def data_dir(self) -> str:
        return self._data_dir

    @property
    def covered_disciplines(self) -> Tuple[str, ...]:
        """The one discipline this adapter sources. A consumer takes narrative events from
        the adapter ONLY -- a missing/failed export stays a visible gap, never a fixture
        fallback."""
        return SOCIAL_EXPORTS_DISCIPLINES

    # -- fetch ---------------------------------------------------------------- #
    def fetch_events(self, *, watchlist=(), themes=(),
                     now: str = "") -> Tuple[Tuple[RealityEvent, ...], SourceAdapterResult]:
        """Read every ``social_export_*.json`` under ``data_dir``. OFFLINE, scope-enforced.

        Only posts matching a REQUESTED ticker/theme are emitted; a requested subject with
        no coverage, a missing directory/file, or a malformed file/entry becomes an explicit
        error/gap NAMING it -- never a crash, never a fabricated value, never demo data.
        """
        state = {"parse_failed": False, "missing": 0}
        events: List[RealityEvent] = []
        refs: List[str] = []
        warnings: List[str] = []
        errors: List[str] = []
        gaps: List[str] = []

        watch = _normalise_tickers(watchlist)
        requested_themes = _normalise_themes(themes)
        theme_norms = {_norm_theme(t): t for t in requested_themes}

        if not watch and not requested_themes:
            gaps.append(
                "empty watchlist AND empty themes: the social-exports adapter emits only "
                "scope-matched posts and was given no scope -- nothing read, nothing "
                "fabricated")
            return (), self._result("skipped", refs, events, warnings, errors, gaps, now)

        if not os.path.isdir(self._data_dir):
            errors.append(
                "source_unavailable: data_dir not found: {0}".format(self._data_dir))
            self._coverage_gaps(watch, requested_themes, (), set(), gaps)
            return (), self._result("failed", refs, events, warnings, errors, gaps, now)

        names = sorted(
            n for n in os.listdir(self._data_dir)
            if n.startswith(SOCIAL_EXPORT_FILE_PREFIX) and n.endswith(".json")
            and os.path.isfile(os.path.join(self._data_dir, n)))
        if not names:
            state["missing"] += 1
            gaps.append(
                "no social export files ({0}*.json) under {1}: discipline narrative has "
                "NO social-export coverage this run -- visible gap, never fabricated, no "
                "silent demo fallback".format(SOCIAL_EXPORT_FILE_PREFIX, self._data_dir))

        for name in names:
            doc, ref = self._load_export(name, refs, errors, gaps, state)
            if doc is None:
                continue
            self._read_posts(doc, name, ref, watch, theme_norms, events, warnings,
                             errors, gaps, state, now)

        covered_tickers = {c for e in events for c in e.affected_companies}
        covered_theme_norms = {_norm_theme(t) for e in events for t in e.affected_themes}
        state["missing"] += self._coverage_gaps(
            watch, requested_themes, covered_tickers, covered_theme_norms, gaps)

        problems = state["parse_failed"] or state["missing"] > 0
        if events:
            status = "partial" if problems else "success"
        elif problems:
            status = "failed"
        else:
            status = "partial"
            gaps.append(
                "social export files under {0} delivered no scope-matched events -- "
                "visible gap, nothing fabricated".format(self._data_dir))

        events.sort(key=lambda e: e.event_id)
        return tuple(events), self._result(
            status, refs, events, warnings, errors, gaps, now)

    # -- one local file: bytes -> sha256 ref -> parsed JSON object -------------- #
    def _load_export(self, name: str, refs: List[str], errors: List[str],
                     gaps: List[str],
                     state: Dict[str, int]) -> Tuple[Optional[Dict], str]:
        path = os.path.join(self._data_dir, name)
        with open(path, "rb") as fh:
            raw = fh.read()
        ref = "localfile:{0}#sha256={1}".format(
            name, hashlib.sha256(raw).hexdigest()[:16])
        refs.append(ref)
        try:
            doc = json.loads(raw.decode("utf-8"))
            if not isinstance(doc, dict):
                raise ValueError("a social export file must be a JSON object")
            posts = doc.get("posts")
            if not isinstance(posts, list):
                raise ValueError("a social export file must carry a 'posts' list")
        except Exception as exc:  # malformed file -> parse_error, NEVER fabricated events
            state["parse_failed"] = True
            errors.append("parse_error: {0}: {1}: {2}".format(
                name, type(exc).__name__, exc))
            gaps.append(
                "malformed social export file {0} (parse_error): its posts have NO "
                "coverage this run -- visible gap, nothing fabricated".format(name))
            return None, ref
        return doc, ref

    # -- posts ------------------------------------------------------------------ #
    def _read_posts(self, doc: Dict, name: str, ref: str, watch: Tuple[str, ...],
                    theme_norms: Dict[str, str], events: List[RealityEvent],
                    warnings: List[str], errors: List[str], gaps: List[str],
                    state: Dict[str, int], now: str) -> None:
        as_of = str(doc.get("as_of", "") or "")
        if as_of and now and _parse_iso(as_of) is None:
            warnings.append(
                "unparsable as_of {0!r} in {1}: staleness cannot be assessed from the "
                "file -- surfaced, not guessed".format(as_of, name))
        for index, entry in enumerate(doc.get("posts", [])):
            if not isinstance(entry, dict):
                self._reject_entry(name, index, "post must be a JSON object",
                                   errors, gaps, state)
                continue
            try:
                event = self._event_from_post(
                    entry, index, name=name, ref=ref, as_of=as_of, watch=watch,
                    theme_norms=theme_norms, warnings=warnings, now=now)
            except Exception as exc:  # malformed entry -> parse_error, per entry
                self._reject_entry(name, index, "{0}: {1}".format(
                    type(exc).__name__, exc), errors, gaps, state)
                continue
            if event is not None:
                events.append(event)

    def _event_from_post(self, entry: Dict, index: int, *, name: str, ref: str,
                         as_of: str, watch: Tuple[str, ...],
                         theme_norms: Dict[str, str], warnings: List[str],
                         now: str) -> Optional[RealityEvent]:
        """One weak narrative RealityEvent from one export post -- or None when the post is
        OUT OF SCOPE (no requested ticker/theme matched: skipped, never emitted).

        Raises for a malformed entry (handled by the caller as a per-entry parse error).
        Authority is ``rumor`` unconditionally; the account type flavours the claim only.
        """
        text = _text_of(entry, "text")
        if not text:
            raise ValueError("missing post text")

        post_tickers = tuple(t.upper() for t in _str_list(entry, "tickers"))
        post_themes = tuple(_str_list(entry, "themes"))

        # -- SCOPE ENFORCEMENT (the 014D rule): only requested subjects flow ---------- #
        matched_tickers = tuple(t for t in watch if t in post_tickers)
        matched_themes = tuple(
            th for th in post_themes if _norm_theme(th) in theme_norms)
        if not matched_tickers and not matched_themes:
            return None                      # unrequested subject: skipped, never emitted

        handle = _text_of(entry, "author_handle", "handle").lstrip("@")
        author_type = _text_of(entry, "author_type").lower()
        account_gaps: List[str] = []
        if author_type == "":
            author_type = "unknown"
            account_gaps.append(
                "author_type missing on {0} posts[{1}]: treated as unknown (claim stays "
                "rumor) -- surfaced, never assumed upward".format(name, index))
        elif author_type not in SOCIAL_EXPORT_ACCOUNT_TYPES:
            account_gaps.append(
                "author_type {0!r} on {1} posts[{2}] not recognised (known: {3}): treated "
                "as unknown (claim stays rumor) -- surfaced, never assumed "
                "upward".format(author_type, name, index,
                                ", ".join(SOCIAL_EXPORT_ACCOUNT_TYPES)))
            author_type = "unknown"

        claim_status, half_life = _ACCOUNT_CLAIM[author_type]
        event_type, source_token = _ACCOUNT_EVENT[author_type]
        if author_type == "unknown" and not matched_tickers and matched_themes:
            event_type, source_token = "theme_mention_spike", "theme_mention"

        # -- numeric context: units always; a bad value rejects the entry ------------- #
        numeric: List[Tuple[str, object, str]] = []
        for key in sorted(_POST_NUMERIC_UNITS):
            value = entry.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(
                    "{0} must be numeric, got {1!r}".format(key, value))
            numeric.append((key, value, _POST_NUMERIC_UNITS[key]))

        # -- bot / promoter risk: VISIBLE, never silently filtered -------------------- #
        bot_risk = entry.get("bot_risk_pct")
        conflicts: List[str] = []
        risk_note = ""
        if isinstance(bot_risk, (int, float)) and not isinstance(bot_risk, bool) \
                and bot_risk >= PROMOTER_BOT_RISK_VISIBLE_PCT:
            subject = (matched_tickers or matched_themes)[0]
            risk_note = ("PROMOTER/BOT RISK ({0:.0f}% bot-risk): "
                         "coordinated/inauthentic amplification suspected -- ".format(
                             float(bot_risk)))
            conflicts.append(
                "PROMOTER/BOT RISK: post on {0} carries bot_risk_pct={1:.0f} (>= {2}) -- "
                "attention is likely inauthentic; NOT evidence of a fact, never silently "
                "filtered".format(subject, float(bot_risk),
                                  PROMOTER_BOT_RISK_VISIBLE_PCT))
            account_gaps.append(
                "promoter/bot risk ({0:.0f}%) reduces reliability of the {1} narrative -- "
                "treat mention velocity as suspect, not corroboration".format(
                    float(bot_risk), subject))

        # -- staleness: posted_at, falling back to the file's as_of ------------------- #
        posted_at = _text_of(entry, "posted_at")
        if posted_at and now and _parse_iso(posted_at) is None:
            warnings.append(
                "unparsable posted_at {0!r} on {1} posts[{2}]: staleness assessed from "
                "the file as_of instead -- surfaced, not guessed".format(
                    posted_at, name, index))
        basis = posted_at if _parse_iso(posted_at) is not None else as_of
        stale = _is_stale(basis, now)
        if stale:
            warnings.append(
                "stale post {0} posts[{1}] ({2}; now {3}, threshold {4}h): marked stale "
                "-- preserved, never dropped, never silently refreshed".format(
                    name, index, basis, now, SOCIAL_EXPORT_STALE_AFTER_HOURS))
        if stale:
            freshness = "stale"
        elif _parse_iso(basis) is not None:
            freshness = "recent"
        else:
            freshness = ""                    # unknown timing -> explicit gap sentinel

        # NOTE: the unknown label deliberately avoids the 012H sensor's rumor-propagation
        # account tokens so a plain mention spike classifies as a Watchlist/Theme Mention
        # (still rumor claim + rumor authority) rather than being force-read as a rumor.
        who = {
            "company_official": "official company account",
            "journalist": "journalist/source account",
            "expert": "expert account",
            "unknown": "unattributed account",
        }[author_type]
        subject_text = ", ".join(matched_tickers + matched_themes)
        observed = "{0}X/social export post by {1}{2} on {3}: {4}".format(
            risk_note, who, " @{0}".format(handle) if handle else "", subject_text, text)

        subject_slug = _slug((matched_tickers or matched_themes)[0])
        excerpt = "socialexport:{0}#posts[{1}]".format(name, index)
        return RealityEvent(
            event_id="socialexport.{0}.{1}.{2}".format(
                subject_slug, event_type, _sha12(name, index, text)),
            timestamp=(posted_at or as_of or now),
            source_id="x_export.{0}.{1}".format(source_token, _slug(handle or "anon")),
            source_type="social_export",
            source_authority="rumor",         # ALWAYS rumor -- X/social never confirms a fact
            claim_status=claim_status,        # account FLAVOUR only, never verified
            raw_payload_ref=ref,
            discipline="narrative",
            event_type=event_type,
            affected_companies=matched_tickers,
            affected_themes=matched_themes,
            observed_fact=observed,
            company_claim=text if claim_status == "company_claim" else "",
            numeric_values=tuple(numeric),
            text_excerpt_refs=(excerpt,),
            evidence_refs=(excerpt,),
            source_refs=(ref,),
            confidence_label="very_low" if risk_note else "low",  # social starts weak, always
            freshness_label=freshness,
            half_life=half_life,
            conflicts=tuple(conflicts),
            data_gaps=tuple(account_gaps),
        )

    # -- coverage / rejection helpers ----------------------------------------------- #
    def _coverage_gaps(self, watch, requested_themes, covered_tickers,
                       covered_theme_norms, gaps: List[str]) -> int:
        """NAMED gap per requested ticker/theme with no social-export coverage."""
        missing = 0
        for ticker in watch:
            if ticker not in covered_tickers:
                missing += 1
                gaps.append(
                    "watchlist ticker {0} has NO social-export (narrative) coverage this "
                    "run under {1} -- visible gap, never fabricated, no silent demo "
                    "fallback".format(ticker, self._data_dir))
        for theme in requested_themes:
            if _norm_theme(theme) not in covered_theme_norms:
                missing += 1
                gaps.append(
                    "requested theme '{0}' has NO social-export (narrative) coverage this "
                    "run under {1} -- visible gap, never fabricated, no silent demo "
                    "fallback".format(theme, self._data_dir))
        return missing

    def _reject_entry(self, name: str, index, reason: str, errors: List[str],
                      gaps: List[str], state: Dict[str, int]) -> None:
        state["parse_failed"] = True
        errors.append("parse_error: {0} posts[{1}]: {2}".format(name, index, reason))
        gaps.append(
            "invalid post posts[{0}] in {1} rejected (parse_error) -- surfaced, never "
            "silently repaired".format(index, name))

    # -- result builder --------------------------------------------------------------- #
    def _result(self, status: str, refs: List[str], events: List[RealityEvent],
                warnings: List[str], errors: List[str], gaps: List[str],
                now: str) -> SourceAdapterResult:
        run_id = deterministic_adapter_run_id(
            SOCIAL_EXPORTS_ADAPTER_ID,
            [now] + sorted(refs) + sorted(errors) + sorted(gaps))
        return SourceAdapterResult(
            adapter_id=SOCIAL_EXPORTS_ADAPTER_ID,
            run_id=run_id,
            status=status,
            raw_payload_refs=tuple(dict.fromkeys(refs)),
            events_created=len(events),
            warnings=tuple(dict.fromkeys(warnings)),
            errors=tuple(dict.fromkeys(errors)),
            data_gaps=tuple(dict.fromkeys(gaps)),
            credentials_status="not_required",   # local files: no credential exists to check
            rate_limit_status="ok",              # a local filesystem read cannot be throttled
            source_health=_STATUS_TO_HEALTH[status])
