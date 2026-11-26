"""C-FUSE-GATE: pre-trade session gate in front of the FUSE-1 engine.

The FUSE-1 engine (``fuse_engine``) does not derive the trading session
itself. ``V7`` trips unless the caller passes ``session_time == "regular"``,
and ``O2`` trips on the calendar and exchange status tokens it is given.
This module derives those inputs from a timestamp and published XNYS
calendar session records (``csa22`` format), so every caller classifies the
session the same way.

Rules (US 23/5 isolation, effective 2026-12-06):

* Orders are allowed only inside the core regular session, ``[open_utc,
  order_cutoff_utc)`` of an XNYS trading day (09:30-16:00 ET, 13:00 ET on a
  half day). Pre-market, after-hours and the 23/5 overnight window never
  allow orders.
* The engine reads ``session_calendar_status`` as a *day-level* fact: it also
  tells V1, L4 and other daily breakers whether a trading session occurred.
  The gate therefore reports ``open`` for the whole of a trading day (a half
  day reports ``half_day_cutoff`` once its cutoff has passed, which O2 trips
  on without marking the day closed), and ``closed``, ``holiday`` or
  ``market_closed`` only for non-trading days. Time-of-day order blocking is
  carried by V7's ``session_time``, never by the calendar status, so an
  end-of-day evaluation still processes the day's breakers.
* ``exchange_status`` must likewise be the venue's day-level status for the
  trade date, observed independently of the calendar; it can only veto.
* The 23/5 overnight window runs 21:00-04:00 ET from 2026-12-06 21:00 ET
  onward, leading into the next trading day; 20:00-21:00 ET is the venue
  maintenance pause and is ``closed``.
* Activity at or after 21:00 ET is attributed to the next trading day
  (``T+1``), so reconciliation can keep the core-session EOD snapshot apart
  from overnight activity.
* Calendar data is trusted only as a whole published file whose SHA-256 is
  pinned in this module (``PINNED_CALENDARS``); callers cannot supply
  individual session records.
* Every malformed, missing, mismatched or inconsistent input fails closed:
  no orders, ``session_time`` other than ``regular``, and an explicit reason.

The gate only computes and records. It never places orders, arms a breaker
or changes a parameter, and it does not modify the digest-pinned engine.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Any, Iterable, Mapping, Optional
from zoneinfo import ZoneInfo

GATE_VERSION = "c-fuse-gate/v1"
EXCHANGE = "XNYS"
TIMEZONE = "America/New_York"

CORE_SESSION_OPEN = "core_session_open"
PRE_MARKET_EXTENDED = "pre_market_extended"
AFTER_HOURS_EXTENDED = "after_hours_extended"
EXTENDED_OVERNIGHT_OPEN = "extended_overnight_open"
CLOSED = "closed"
VENUE_WINDOWS = (
    CORE_SESSION_OPEN,
    PRE_MARKET_EXTENDED,
    AFTER_HOURS_EXTENDED,
    EXTENDED_OVERNIGHT_OPEN,
    CLOSED,
)

# Engine O2 status tokens (fuse_engine.rows_ops.VALID_CALENDAR_STATUSES).
ENGINE_EXCHANGE_STATUSES = frozenset(
    {"open", "closed", "holiday", "half_day", "half_day_cutoff", "market_closed"}
)

# Published calendar files the gate accepts, pinned by content. Adding a
# calendar year (for example csa22-v3 for 2027) is a reviewed change here.
PINNED_CALENDARS = MappingProxyType({
    "csa22-v2": MappingProxyType({
        "spec_digest": "2ba8cd7684c361209df68bfa2e10004c1f9922a645c7ec55d421fda520561798",
        "expected_file": "expected-2026.json",
        "expected_sha256": "d3145792a7e5aabe5d0745aa266263930f0bf37c88e6cf3b317009bcdb54bb07",
    }),
})

_MAINTENANCE_START = time(20, 0)
_OVERNIGHT_START = time(21, 0)
# US 23/5 overnight trading takes effect with the session opening Sunday 2026-12-06 21:00 ET.
_OVERNIGHT_EFFECTIVE_LOCAL = datetime(2026, 12, 6, 21, 0)
_PRE_MARKET_START = time(4, 0)
_NEXT_DAY_ATTRIBUTION_START = time(21, 0)
_SESSION_STATES = frozenset({"regular", "half_day", "closed", "unscheduled_closure"})
# XNYS core-session bounds by session state (New York local time).
_CORE_OPEN_LOCAL = time(9, 30)
_CORE_CLOSE_LOCAL = {"regular": time(16, 0), "half_day": time(13, 0)}
_MAX_SUCCESSOR_SCAN_DAYS = 14
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_HHMM_RE = re.compile(r"(?:[01]\d|2[0-3]):[0-5]\d")
# RFC 3339 instant with an explicit, in-range offset; fromisoformat alone
# normalises some invalid offsets (for example ``+00:99``) instead of failing.
_INSTANT_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?"
    r"(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)"
)
_NY = ZoneInfo(TIMEZONE)


class GateInputError(ValueError):
    """A gate input is malformed; the caller must fail closed."""


def _parse_utc(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise GateInputError(f"{label}_missing")
    if not _INSTANT_RE.fullmatch(value):
        raise GateInputError(f"{label}_invalid")
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(text)
        utc = parsed.astimezone(timezone.utc)
        # Every later step converts to New York time; reject instants that cannot be.
        utc.astimezone(_NY)
    except (OverflowError, ValueError) as exc:
        raise GateInputError(f"{label}_out_of_range") from exc
    return utc


def _parse_minute_utc(value: Any, label: str) -> datetime:
    """Parse a calendar instant that must fall exactly on a minute boundary."""
    parsed = _parse_utc(value, label)
    if parsed.second or parsed.microsecond:
        raise GateInputError(f"{label}_not_minute_aligned")
    return parsed


def _token(value: Any, allowed: frozenset) -> Optional[str]:
    """Return ``value`` if it is an allowed string token, else ``None``."""
    return value if isinstance(value, str) and value in allowed else None


def _parse_date(value: Any, label: str) -> date:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise GateInputError(f"{label}_invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise GateInputError(f"{label}_invalid") from exc


def _hhmm(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _HHMM_RE.fullmatch(value):
        raise GateInputError(f"{label}_invalid")
    return value


def validate_session(session: Any, trusted_spec_digest: Any) -> dict:
    """Validate one csa22 calendar session record and return its parsed form.

    ``trusted_spec_digest`` is the calendar digest the caller has verified
    and pinned; a record published under any other digest is rejected.
    """
    if not isinstance(trusted_spec_digest, str) or not _DIGEST_RE.fullmatch(trusted_spec_digest):
        raise GateInputError("trusted_spec_digest_invalid")
    if not isinstance(session, Mapping):
        raise GateInputError("session_missing")
    if session.get("exchange") != EXCHANGE:
        raise GateInputError("session_exchange_invalid")
    if session.get("timezone") != TIMEZONE:
        raise GateInputError("session_timezone_invalid")
    if not isinstance(session.get("calendar_version"), str) or not session["calendar_version"]:
        raise GateInputError("session_calendar_version_missing")
    if not isinstance(session.get("spec_digest"), str) or not _DIGEST_RE.fullmatch(session["spec_digest"]):
        raise GateInputError("session_spec_digest_invalid")
    if session["spec_digest"] != trusted_spec_digest:
        raise GateInputError("session_spec_digest_untrusted")
    trade_date = _parse_date(session.get("trade_date"), "session_trade_date")
    coverage_start = _parse_date(session.get("coverage_start_date"), "session_coverage_start_date")
    coverage_end = _parse_date(session.get("coverage_end_date"), "session_coverage_end_date")
    if not coverage_start <= trade_date <= coverage_end:
        raise GateInputError("session_outside_coverage")
    state = _token(session.get("session_state"), _SESSION_STATES)
    if state is None:
        raise GateInputError("session_state_invalid")
    is_trading_day = session.get("is_trading_day")
    blocks_orders = session.get("blocks_orders")
    if not isinstance(is_trading_day, bool) or not isinstance(blocks_orders, bool):
        raise GateInputError("session_flags_invalid")
    if is_trading_day != (state in ("regular", "half_day")):
        raise GateInputError("session_state_inconsistent")
    # csa22: trading days never block orders and non-trading days always do.
    if blocks_orders == is_trading_day:
        raise GateInputError("session_flags_inconsistent")
    parsed = {
        "trade_date": trade_date,
        "session_state": state,
        "is_trading_day": is_trading_day,
        "blocks_orders": blocks_orders,
        "calendar_version": session["calendar_version"],
        "spec_digest": session["spec_digest"],
        "open_utc": None,
        "close_utc": None,
        "order_cutoff_utc": None,
    }
    if not is_trading_day:
        for key in ("open_utc", "close_utc", "order_cutoff_utc", "order_window", "open_local", "close_local", "cutoff_local"):
            if session.get(key) is not None:
                raise GateInputError("session_times_on_closed_day")
        return parsed

    open_utc = _parse_minute_utc(session.get("open_utc"), "session_open_utc")
    close_utc = _parse_minute_utc(session.get("close_utc"), "session_close_utc")
    cutoff_utc = _parse_minute_utc(session.get("order_cutoff_utc"), "session_order_cutoff_utc")
    # An empty order window (cutoff at the open) is valid and allows no orders.
    if not open_utc <= cutoff_utc <= close_utc:
        raise GateInputError("session_times_inconsistent")
    open_local = open_utc.astimezone(_NY)
    close_local = close_utc.astimezone(_NY)
    cutoff_local = cutoff_utc.astimezone(_NY)
    if open_local.date() != trade_date or close_local.date() != trade_date:
        raise GateInputError("session_times_off_trade_date")
    # The record may not widen the core session: 09:30 ET open, 16:00 ET
    # close (13:00 ET on a half day), whatever its UTC fields say.
    if open_local.time() != _CORE_OPEN_LOCAL or close_local.time() != _CORE_CLOSE_LOCAL[state]:
        raise GateInputError("session_times_not_core_hours")
    # Every field that states the order window must agree with the one used.
    for key, expected in (("open_local", open_local), ("close_local", close_local), ("cutoff_local", cutoff_local)):
        if _hhmm(session.get(key), f"session_{key}") != expected.strftime("%H:%M"):
            raise GateInputError("session_local_times_inconsistent")
    window = session.get("order_window")
    if not isinstance(window, Mapping) or set(window) != {"start_utc", "end_utc", "half_open"}:
        raise GateInputError("session_order_window_invalid")
    if (
        window["half_open"] is not True
        or _parse_minute_utc(window["start_utc"], "session_order_window_start") != open_utc
        or _parse_minute_utc(window["end_utc"], "session_order_window_end") != cutoff_utc
    ):
        raise GateInputError("session_order_window_inconsistent")
    parsed.update(open_utc=open_utc, close_utc=close_utc, order_cutoff_utc=cutoff_utc)
    return parsed


class TrustedCalendar:
    """XNYS sessions loaded only from pinned, byte-verified calendar files."""

    __slots__ = ("_sessions", "_versions")

    def __init_subclass__(cls, **kwargs):
        raise TypeError("TrustedCalendar cannot be subclassed")

    def __init__(self, sessions: Mapping[date, dict], versions: Iterable[str], _token: object = None):
        if _token is not _CONSTRUCT:
            raise TypeError("use load_trusted_calendar()")
        self._sessions = MappingProxyType(dict(sessions))
        self._versions = tuple(versions)

    @property
    def versions(self) -> tuple:
        return self._versions

    def session(self, day: date) -> Optional[dict]:
        record = self._sessions.get(day)
        return dict(record) if record is not None else None


_CONSTRUCT = object()


def load_trusted_calendar(documents: Mapping[str, bytes]) -> TrustedCalendar:
    """Verify published calendar files and return the sessions they define.

    ``documents`` maps a pinned calendar version (``csa22-v2``) to the raw
    bytes of its ``expected-<year>.json``. Each file must match its pinned
    SHA-256 exactly, and every session in it must validate; coverage windows
    of different versions may not overlap.
    """
    if not isinstance(documents, Mapping) or not documents:
        raise GateInputError("calendar_documents_missing")
    sessions: dict = {}
    for version, raw in documents.items():
        pin = PINNED_CALENDARS.get(version) if isinstance(version, str) else None
        if pin is None:
            raise GateInputError("calendar_version_not_pinned")
        # Only immutable bytes: the object hashed is the object parsed.
        if type(raw) is not bytes:
            raise GateInputError("calendar_document_not_bytes")
        if hashlib.sha256(raw).hexdigest() != pin["expected_sha256"]:
            raise GateInputError("calendar_document_digest_mismatch")
        try:
            doc = json.loads(raw)
        except ValueError as exc:
            raise GateInputError("calendar_document_invalid") from exc
        if (
            not isinstance(doc, Mapping)
            or doc.get("calendar_version") != version
            or doc.get("spec_digest") != pin["spec_digest"]
            or doc.get("status") != "published"
            or not isinstance(doc.get("sessions"), Mapping)
        ):
            raise GateInputError("calendar_document_invalid")
        start = _parse_date(doc.get("coverage_start_date"), "calendar_coverage_start_date")
        end = _parse_date(doc.get("coverage_end_date"), "calendar_coverage_end_date")
        expected_days = (end - start).days + 1
        if doc.get("day_count") != expected_days or len(doc["sessions"]) != expected_days:
            raise GateInputError("calendar_document_incomplete")
        for key, record in doc["sessions"].items():
            parsed = validate_session(record, pin["spec_digest"])
            if (
                parsed["trade_date"].isoformat() != key
                or record.get("calendar_version") != version
                or not start <= parsed["trade_date"] <= end
                or record.get("coverage_start_date") != doc["coverage_start_date"]
                or record.get("coverage_end_date") != doc["coverage_end_date"]
            ):
                raise GateInputError("calendar_document_invalid")
            if parsed["trade_date"] in sessions:
                raise GateInputError("calendar_coverage_overlap")
            sessions[parsed["trade_date"]] = parsed
    return TrustedCalendar(sessions, sorted(documents), _token=_CONSTRUCT)


def _next_calendar_day(day: date) -> Optional[date]:
    return None if day >= date.max else day + timedelta(days=1)


def _successor_session(calendar: TrustedCalendar, day: date) -> Optional[dict]:
    """Return the immediately following XNYS trading session, or ``None``.

    Every calendar date between ``day`` and its successor must be covered by
    the trusted calendar; a gap leaves the successor unknown rather than
    guessed.
    """
    for _ in range(_MAX_SUCCESSOR_SCAN_DAYS):
        nxt_day = _next_calendar_day(day)
        if nxt_day is None:
            return None
        day = nxt_day
        record = calendar.session(day)
        if record is None:
            return None
        if record["is_trading_day"]:
            return record
    return None


def _overnight_leads_into(calendar: TrustedCalendar, local: datetime, parsed: dict) -> bool:
    """Whether a local instant in the overnight hours is a live 23/5 session."""
    if local.replace(tzinfo=None) < _OVERNIGHT_EFFECTIVE_LOCAL:
        return False
    if local.time() >= _OVERNIGHT_START:
        # The evening leg leads into the next calendar day's session.
        following = _next_calendar_day(parsed["trade_date"])
        nxt = calendar.session(following) if following is not None else None
        return nxt is not None and nxt["is_trading_day"]
    # The early-morning leg leads into this day's session.
    return parsed["is_trading_day"]


def _classify(ts: datetime, parsed: dict, calendar: TrustedCalendar) -> str:
    local = ts.astimezone(_NY)
    if local.date() != parsed["trade_date"]:
        raise GateInputError("session_date_mismatch")
    local_t = local.time()
    if _MAINTENANCE_START <= local_t < _OVERNIGHT_START:
        return CLOSED  # venue maintenance pause
    if local_t >= _OVERNIGHT_START or local_t < _PRE_MARKET_START:
        return EXTENDED_OVERNIGHT_OPEN if _overnight_leads_into(calendar, local, parsed) else CLOSED
    if not parsed["is_trading_day"]:
        return CLOSED
    if parsed["open_utc"] <= ts < parsed["close_utc"]:
        return CORE_SESSION_OPEN
    if ts < parsed["open_utc"]:
        return PRE_MARKET_EXTENDED
    return AFTER_HOURS_EXTENDED


def _resolve(timestamp_utc: Any, calendar: Any) -> tuple:
    if type(calendar) is not TrustedCalendar:
        raise GateInputError("calendar_untrusted")
    ts = _parse_utc(timestamp_utc, "timestamp")
    parsed = calendar.session(ts.astimezone(_NY).date())
    if parsed is None:
        raise GateInputError("session_outside_calendar_coverage")
    return ts, parsed


def classify_venue_window(timestamp_utc: str, calendar: TrustedCalendar) -> str:
    """Classify a timestamp against the trusted calendar session of its local date."""
    ts, parsed = _resolve(timestamp_utc, calendar)
    return _classify(ts, parsed, calendar)


def _calendar_status(parsed: dict, ts: datetime) -> str:
    if not parsed["is_trading_day"]:
        if parsed["session_state"] == "unscheduled_closure":
            return "market_closed"
        return "holiday" if parsed["trade_date"].weekday() < 5 else "closed"
    # Day-level: a trading day stays ``open`` before and after its core window.
    if parsed["session_state"] == "half_day" and ts >= parsed["order_cutoff_utc"]:
        return "half_day_cutoff"
    return "open"


def _closed_decision(reason: str, timestamp_utc: Any, exchange_status: Any) -> dict:
    return {
        "gate_version": GATE_VERSION,
        "timestamp_utc": timestamp_utc if isinstance(timestamp_utc, str) else None,
        "trade_date": None,
        "venue_window": CLOSED,
        "orders_allowed": False,
        "reason": reason,
        "activity_trade_date": None,
        "calendar_version": None,
        "spec_digest": None,
        "engine_inputs": {
            "session_time": "outside_regular",
            "session_calendar_status": None,
            "exchange_status": _token(exchange_status, ENGINE_EXCHANGE_STATUSES),
        },
    }


def pre_trade_gate(timestamp_utc: str, calendar: TrustedCalendar, exchange_status: Any) -> dict:
    """Return the gate decision and the FUSE engine session inputs.

    ``calendar`` comes from ``load_trusted_calendar``; the session is looked up
    by the timestamp's New York local date. ``exchange_status`` is the venue
    status observed independently of the calendar, as an engine O2 token; it
    can only veto. Missing ``session_calendar_status`` or ``exchange_status``
    in the result makes the engine's O2 fail closed by itself.
    """
    try:
        ts, parsed = _resolve(timestamp_utc, calendar)
        window = _classify(ts, parsed, calendar)
    except GateInputError as exc:
        return _closed_decision(str(exc), timestamp_utc, exchange_status)

    calendar_status = _calendar_status(parsed, ts)
    local_t = ts.astimezone(_NY).time()
    if local_t >= _OVERNIGHT_START:
        nxt = _successor_session(calendar, parsed["trade_date"])
        activity_trade_date = nxt["trade_date"].isoformat() if nxt is not None else None
    elif parsed["is_trading_day"]:
        activity_trade_date = parsed["trade_date"].isoformat()
    else:
        activity_trade_date = None

    exchange_token = _token(exchange_status, ENGINE_EXCHANGE_STATUSES)
    if exchange_token is None:
        reason = "exchange_status_invalid" if exchange_status is not None else "exchange_status_missing"
    elif parsed["blocks_orders"]:
        reason = "calendar_blocks_orders"
    elif window != CORE_SESSION_OPEN:
        reason = "outside_core_session"
    elif not ts < parsed["order_cutoff_utc"]:
        reason = "past_order_cutoff"
    elif exchange_token != "open":
        reason = "exchange_not_open"
    else:
        reason = "none"
    orders_allowed = reason == "none"

    return {
        "gate_version": GATE_VERSION,
        "timestamp_utc": timestamp_utc,
        "trade_date": parsed["trade_date"].isoformat(),
        "venue_window": window,
        "orders_allowed": orders_allowed,
        "reason": reason,
        "activity_trade_date": activity_trade_date,
        "calendar_version": parsed["calendar_version"],
        "spec_digest": parsed["spec_digest"],
        "engine_inputs": {
            # V7 passes only when the order would be sent inside the core window.
            "session_time": "regular" if orders_allowed else "outside_regular",
            "session_calendar_status": calendar_status,
            "exchange_status": exchange_token,
        },
    }


def gate_engine_inputs(
    validated_inputs: Any,
    timestamp_utc: str,
    calendar: TrustedCalendar,
    exchange_status: Any,
) -> tuple:
    """Run the gate and return ``(engine_inputs, decision)``.

    The decision is computed here from the trusted calendar; no caller-supplied
    decision is ever applied. O2 reads ``session_calendar_status`` and
    ``exchange_status`` at the top level. V7 reads ``session_time`` per symbol
    from ``funds``, then ``quotes``, then ``symbols``; the gate's token
    overwrites every symbol in all three, so no caller-supplied value survives.
    ``validated_inputs`` is not mutated.
    """
    decision = pre_trade_gate(timestamp_utc, calendar, exchange_status)
    tokens = decision["engine_inputs"]
    out = dict(validated_inputs) if isinstance(validated_inputs, Mapping) else {}
    out["session_calendar_status"] = tokens["session_calendar_status"]
    out["exchange_status"] = tokens["exchange_status"]
    for source in ("funds", "quotes", "symbols"):
        entries = out.get(source)
        if isinstance(entries, Mapping):
            out[source] = {
                symbol: ({**dict(entry), "session_time": tokens["session_time"]} if isinstance(entry, Mapping) else entry)
                for symbol, entry in entries.items()
            }
    return out, decision


__all__ = [
    "AFTER_HOURS_EXTENDED",
    "PINNED_CALENDARS",
    "TrustedCalendar",
    "gate_engine_inputs",
    "load_trusted_calendar",
    "CLOSED",
    "CORE_SESSION_OPEN",
    "ENGINE_EXCHANGE_STATUSES",
    "EXTENDED_OVERNIGHT_OPEN",
    "GATE_VERSION",
    "GateInputError",
    "PRE_MARKET_EXTENDED",
    "VENUE_WINDOWS",
    "classify_venue_window",
    "pre_trade_gate",
    "validate_session",
]
