"""C-FUSE-GATE: pre-trade session gate tests (US 23/5 isolation).

The calendar fixture is the verbatim published csa22-v2 expected-2026.json.
The gate must derive the engine's V7/O2 session inputs consistently and fail
closed on anything it cannot verify.
"""
import copy
import json
import sys
import unittest
from datetime import date
from pathlib import Path

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root))

import src.fuse_gate as fuse_gate  # noqa: E402
from src.fuse_gate import (  # noqa: E402
    AFTER_HOURS_EXTENDED,
    CLOSED,
    CORE_SESSION_OPEN,
    EXTENDED_OVERNIGHT_OPEN,
    PRE_MARKET_EXTENDED,
    GateInputError,
    gate_engine_inputs,
    classify_venue_window,
    load_trusted_calendar,
    pre_trade_gate,
    validate_session,
)
from src.fuse_engine import evaluator as engine  # noqa: E402

RAW = (repo_root / "tests" / "fixtures" / "csa22-v2-expected-2026.json").read_bytes()
DOC = json.loads(RAW)
D = DOC["spec_digest"]
CAL = load_trusted_calendar({"csa22-v2": RAW})


def gate(ts, exchange="open", calendar=CAL):
    return pre_trade_gate(ts, calendar, exchange)


def edited(day, **changes):
    rec = copy.deepcopy(DOC["sessions"][day])
    rec.update(changes)
    return rec


def calendar_with(**overrides):
    """A test-only calendar with edited records, built past the loader on purpose."""
    sessions = {date.fromisoformat(k): validate_session(v, D) for k, v in DOC["sessions"].items()}
    for day, record in overrides.items():
        if record is None:
            sessions.pop(date.fromisoformat(day), None)
        else:
            sessions[date.fromisoformat(day)] = validate_session(record, D)
    return fuse_gate.TrustedCalendar(sessions, ["test"], _token=fuse_gate._CONSTRUCT)


class TestTrustedCalendar(unittest.TestCase):
    def test_loads_pinned_calendar(self):
        self.assertEqual(CAL.versions, ("csa22-v2",))
        self.assertEqual(CAL.session(date(2026, 12, 7))["session_state"], "regular")
        self.assertIsNone(CAL.session(date(2027, 1, 4)))

    def test_rejects_tampered_or_unpinned_documents(self):
        # Codex P1 (round 3): records are bound to the verified file contents, not a self-declared digest.
        tampered = json.loads(RAW)
        tampered["sessions"]["2026-12-24"].update(
            session_state="regular", close_local="16:00", cutoff_local="16:00",
            close_utc="2026-12-24T21:00:00.000Z", order_cutoff_utc="2026-12-24T21:00:00.000Z")
        for label, documents in (
            ("tampered", {"csa22-v2": json.dumps(tampered).encode()}),
            ("one_byte", {"csa22-v2": RAW.replace(b"16:00", b"16:01", 1)}),
            ("unpinned_version", {"csa22-v9": RAW}),
            ("text_not_bytes", {"csa22-v2": RAW.decode()}),
            # Codex P1 (round 4): a mutable buffer could change between hashing and parsing.
            ("bytearray", {"csa22-v2": bytearray(RAW)}),
            ("memoryview", {"csa22-v2": memoryview(RAW)}),
            ("empty", {}),
            ("not_a_mapping", [RAW]),
        ):
            with self.subTest(label=label):
                with self.assertRaises(GateInputError):
                    load_trusted_calendar(documents)

    def test_coverage_binding_is_checked_per_record(self):
        # Codex P2 (round 4): records must carry the document's coverage, and keys must fall inside it.
        import hashlib
        doc = json.loads(RAW)
        doc["sessions"]["2026-06-01"]["coverage_end_date"] = "2027-12-31"
        raw = json.dumps(doc).encode()
        pins = {"csa22-v2": dict(fuse_gate.PINNED_CALENDARS["csa22-v2"], expected_sha256=hashlib.sha256(raw).hexdigest())}
        original = fuse_gate.PINNED_CALENDARS
        fuse_gate.PINNED_CALENDARS = pins
        try:
            with self.assertRaises(GateInputError):
                load_trusted_calendar({"csa22-v2": raw})
        finally:
            fuse_gate.PINNED_CALENDARS = original

    def test_gate_rejects_anything_but_a_trusted_calendar(self):
        for calendar in (DOC, DOC["sessions"], None, {"csa22-v2": RAW}):
            with self.subTest(calendar=type(calendar).__name__):
                d = gate("2026-12-07T15:00:00Z", calendar=calendar)
                self.assertFalse(d["orders_allowed"])
                self.assertEqual(d["reason"], "calendar_untrusted")
        with self.assertRaises(TypeError):
            fuse_gate.TrustedCalendar({}, ["x"])

    def test_outside_coverage_fails_closed(self):
        # csa22-v2 ends 2026-12-31: without a 2027 calendar, 2027 is closed, not guessed.
        d = gate("2027-01-04T15:00:00Z")
        self.assertFalse(d["orders_allowed"])
        self.assertEqual(d["reason"], "session_outside_calendar_coverage")
        # The last covered evening cannot attribute T+1 into the uncovered year.
        self.assertIsNone(gate("2027-01-01T02:30:00Z")["activity_trade_date"])  # Thu 2026-12-31 21:30 ET


class TestVenueWindows(unittest.TestCase):
    def test_regular_day_windows(self):
        # 2026-12-07 is EST: 09:30 ET = 14:30Z, 16:00 ET = 21:00Z.
        cases = [
            ("2026-12-07T08:59:00Z", EXTENDED_OVERNIGHT_OPEN),  # 03:59 ET, leads into Monday
            ("2026-12-07T09:00:00Z", PRE_MARKET_EXTENDED),      # 04:00 ET
            ("2026-12-07T14:29:59Z", PRE_MARKET_EXTENDED),
            ("2026-12-07T14:30:00Z", CORE_SESSION_OPEN),
            ("2026-12-07T20:59:59Z", CORE_SESSION_OPEN),
            ("2026-12-07T21:00:00Z", AFTER_HOURS_EXTENDED),     # 16:00 ET close is exclusive
            ("2026-12-08T00:59:59Z", AFTER_HOURS_EXTENDED),     # 19:59:59 ET
            ("2026-12-08T01:00:00Z", CLOSED),                   # 20:00 ET maintenance pause
            ("2026-12-08T01:59:59Z", CLOSED),
            ("2026-12-08T02:00:00Z", EXTENDED_OVERNIGHT_OPEN),  # 21:00 ET
        ]
        for ts, expected in cases:
            with self.subTest(ts=ts):
                self.assertEqual(classify_venue_window(ts, CAL), expected)

    def test_half_day_closes_at_13_et(self):
        self.assertEqual(classify_venue_window("2026-11-27T17:59:59Z", CAL), CORE_SESSION_OPEN)
        self.assertEqual(classify_venue_window("2026-11-27T18:00:00Z", CAL), AFTER_HOURS_EXTENDED)

    def test_evening_leg_follows_the_session_it_leads_into(self):
        # Sunday evening before Monday is overnight; Friday evening before Saturday is not.
        self.assertEqual(classify_venue_window("2026-12-07T02:00:00Z", CAL), EXTENDED_OVERNIGHT_OPEN)  # Sun 21:00
        self.assertEqual(classify_venue_window("2026-12-07T01:30:00Z", CAL), CLOSED)                   # Sun 20:30 pause
        self.assertEqual(classify_venue_window("2026-12-12T02:00:00Z", CAL), CLOSED)                   # Fri 21:00
        # Christmas Eve evening leads into the Christmas holiday.
        self.assertEqual(classify_venue_window("2026-12-25T02:00:00Z", CAL), CLOSED)

    def test_overnight_policy_starts_on_effective_date(self):
        # Codex P2 (round 3): before 2026-12-06 21:00 ET there is no overnight session.
        self.assertEqual(classify_venue_window("2026-12-04T08:00:00Z", CAL), CLOSED)  # Fri 03:00 ET
        self.assertEqual(classify_venue_window("2026-11-27T02:30:00Z", CAL), CLOSED)  # Thanksgiving 21:30 ET
        self.assertEqual(classify_venue_window("2026-12-07T01:59:00Z", CAL), CLOSED)  # Sun 20:59 ET pause
        self.assertEqual(classify_venue_window("2026-12-07T02:00:00Z", CAL), EXTENDED_OVERNIGHT_OPEN)

    def test_non_trading_daytime_is_closed(self):
        for ts in ("2026-12-05T15:00:00Z", "2026-12-25T15:00:00Z"):
            with self.subTest(ts=ts):
                self.assertEqual(classify_venue_window(ts, CAL), CLOSED)


class TestPreTradeGate(unittest.TestCase):
    def test_core_session_allows_orders_and_feeds_engine_regular(self):
        d = gate("2026-12-07T15:00:00Z")
        self.assertTrue(d["orders_allowed"])
        self.assertEqual(d["reason"], "none")
        self.assertEqual(d["venue_window"], CORE_SESSION_OPEN)
        self.assertEqual(d["engine_inputs"], {"session_time": "regular", "session_calendar_status": "open", "exchange_status": "open"})
        self.assertEqual(d["activity_trade_date"], "2026-12-07")
        self.assertEqual(d["spec_digest"], D)
        self.assertEqual(d["calendar_version"], "csa22-v2")

    def test_outside_core_never_allows_orders(self):
        for ts in ("2026-12-07T14:29:59Z", "2026-12-07T21:00:00Z", "2026-12-08T01:30:00Z", "2026-12-08T03:00:00Z",
                   "2026-12-07T05:00:00Z"):
            with self.subTest(ts=ts):
                d = gate(ts)
                self.assertFalse(d["orders_allowed"])
                self.assertEqual(d["reason"], "outside_core_session")
                self.assertEqual(d["engine_inputs"]["session_time"], "outside_regular")
                # Day-level calendar status: the trading day is still a trading day.
                self.assertEqual(d["engine_inputs"]["session_calendar_status"], "open")

    def test_half_day_open_before_cutoff_and_cutoff_after(self):
        before = gate("2026-12-24T17:00:00Z")
        self.assertTrue(before["orders_allowed"])
        self.assertEqual(before["engine_inputs"]["session_calendar_status"], "open")
        after = gate("2026-12-24T18:30:00Z")
        self.assertFalse(after["orders_allowed"])
        self.assertEqual(after["engine_inputs"]["session_calendar_status"], "half_day_cutoff")

    def test_holiday_and_weekend_status_tokens(self):
        holiday = gate("2026-12-25T15:00:00Z", exchange="holiday")
        self.assertFalse(holiday["orders_allowed"])
        self.assertEqual(holiday["reason"], "calendar_blocks_orders")
        self.assertEqual(holiday["engine_inputs"]["session_calendar_status"], "holiday")
        weekend = gate("2026-12-05T15:00:00Z", exchange="closed")
        self.assertEqual(weekend["engine_inputs"]["session_calendar_status"], "closed")
        # Activity on a non-trading day clears on the next trading day.
        self.assertEqual(weekend["activity_trade_date"], "2026-12-07")
        self.assertEqual(holiday["activity_trade_date"], "2026-12-28")

    def test_unscheduled_closure_maps_to_market_closed(self):
        closure = edited("2026-12-07", session_state="unscheduled_closure", is_trading_day=False, blocks_orders=True,
                         open_utc=None, close_utc=None, order_cutoff_utc=None, order_window=None,
                         open_local=None, close_local=None, cutoff_local=None)
        d = gate("2026-12-07T15:00:00Z", exchange="market_closed", calendar=calendar_with(**{"2026-12-07": closure}))
        self.assertFalse(d["orders_allowed"])
        self.assertEqual(d["engine_inputs"]["session_calendar_status"], "market_closed")

    def test_published_earlier_cutoff_is_honoured(self):
        # A registered cutoff before the close (C-SA-22 rule 2) is carried by the record itself.
        early = edited("2026-12-07", cutoff_local="15:00", order_cutoff_utc="2026-12-07T20:00:00.000Z",
                       order_window={"start_utc": "2026-12-07T14:30:00.000Z", "end_utc": "2026-12-07T20:00:00.000Z", "half_open": True})
        cal = calendar_with(**{"2026-12-07": early})
        self.assertTrue(gate("2026-12-07T19:59:00Z", calendar=cal)["orders_allowed"])
        late = gate("2026-12-07T20:30:00Z", calendar=cal)
        self.assertFalse(late["orders_allowed"])
        self.assertEqual(late["reason"], "past_order_cutoff")
        self.assertEqual(late["engine_inputs"]["session_time"], "outside_regular")

    def test_trading_day_that_blocks_orders_is_inconsistent(self):
        # csa22: trading days never block orders; such a record is rejected outright.
        with self.assertRaises(GateInputError):
            validate_session(edited("2026-12-07", blocks_orders=True), D)

    def test_empty_order_window_is_valid_and_allows_nothing(self):
        # Codex P2 (round 3): a cutoff at the open is a valid session with no order window.
        empty = edited("2026-12-07", cutoff_local="09:30", order_cutoff_utc="2026-12-07T14:30:00.000Z",
                       order_window={"start_utc": "2026-12-07T14:30:00.000Z", "end_utc": "2026-12-07T14:30:00.000Z", "half_open": True})
        d = gate("2026-12-07T15:00:00Z", calendar=calendar_with(**{"2026-12-07": empty}))
        self.assertFalse(d["orders_allowed"])
        self.assertEqual(d["venue_window"], CORE_SESSION_OPEN)
        self.assertEqual(d["reason"], "past_order_cutoff")

    def test_exchange_status_can_only_veto(self):
        d = gate("2026-12-07T15:00:00Z", exchange="closed")
        self.assertFalse(d["orders_allowed"])
        self.assertEqual(d["reason"], "exchange_not_open")
        self.assertFalse(gate("2026-12-25T15:00:00Z", exchange="open")["orders_allowed"])
        for bad in (None, "n/a", True, 1, {}, [], ["open"], 1.5):
            with self.subTest(exchange=bad):
                d = gate("2026-12-07T15:00:00Z", exchange=bad)
                self.assertFalse(d["orders_allowed"])
                self.assertIsNone(d["engine_inputs"]["exchange_status"])

    def test_activity_after_21_et_belongs_to_next_trading_day(self):
        d = gate("2026-12-05T02:00:00Z")  # Fri 2026-12-04 21:00 ET
        self.assertEqual(d["trade_date"], "2026-12-04")
        self.assertEqual(d["activity_trade_date"], "2026-12-07")
        self.assertFalse(d["orders_allowed"])
        # The trade-date boundary is 20:00 ET (IBKR dates 20:00-24:00 fills to the next day).
        self.assertEqual(gate("2026-12-05T00:59:00Z")["activity_trade_date"], "2026-12-04")  # 19:59 ET stays on T
        self.assertEqual(gate("2026-12-05T01:00:00Z")["activity_trade_date"], "2026-12-07")  # 20:00 ET -> next trading day
        self.assertEqual(gate("2026-12-05T01:30:00Z")["activity_trade_date"], "2026-12-07")  # 20:30 ET, venue pause
        self.assertEqual(gate("2026-12-07T02:00:00Z")["activity_trade_date"], "2026-12-07")  # Sun 21:00 ET
        self.assertEqual(gate("2026-11-27T02:00:00Z")["activity_trade_date"], "2026-11-27")  # Thanksgiving 21:00 ET

    def test_t_plus_one_requires_contiguous_coverage(self):
        gap = calendar_with(**{"2026-12-05": None})
        self.assertIsNone(gate("2026-12-05T02:00:00Z", calendar=gap)["activity_trade_date"])

    def test_session_records_cannot_widen_or_blur_the_window(self):
        early_window = {"start_utc": "2026-12-07T14:30:00.000Z", "end_utc": "2026-12-07T14:59:00.000Z", "half_open": True}
        cases = (
            ("open_before_core", {"open_utc": "2026-12-07T10:00:00.000Z"}),
            ("close_after_core", {"close_utc": "2026-12-07T23:00:00.000Z", "order_cutoff_utc": "2026-12-07T23:00:00.000Z"}),
            ("cutoff_local", {"cutoff_local": "09:59"}),
            ("order_window_end", {"order_window": early_window}),
            ("window_not_half_open", {"order_window": dict(DOC["sessions"]["2026-12-07"]["order_window"], half_open=False)}),
            ("window_extra_key", {"order_window": dict(DOC["sessions"]["2026-12-07"]["order_window"], extra=1)}),
            ("window_missing", {"order_window": None}),
            ("open_local", {"open_local": "08:00"}),
            ("cutoff_local_missing", {"cutoff_local": None}),
            # Codex P1 (round 3): sub-minute instants cannot hide behind HH:MM fields.
            ("cutoff_sub_minute", {"cutoff_local": "10:00", "order_cutoff_utc": "2026-12-07T15:00:59.999Z",
                                   "order_window": {"start_utc": "2026-12-07T14:30:00.000Z", "end_utc": "2026-12-07T15:00:59.999Z", "half_open": True}}),
            ("open_sub_minute", {"open_utc": "2026-12-07T14:30:30.000Z"}),
        )
        for label, changes in cases:
            with self.subTest(label=label):
                with self.assertRaises(GateInputError):
                    validate_session(edited("2026-12-07", **changes), D)
        half = edited("2026-12-24", close_utc="2026-12-24T21:00:00.000Z", order_cutoff_utc="2026-12-24T21:00:00.000Z")
        with self.assertRaises(GateInputError):
            validate_session(half, D)

    def test_malformed_records_are_rejected(self):
        cases = [(key, edited("2026-12-07", **{key: value})) for key, value in (
            ("exchange", "XHKG"), ("timezone", "UTC"), ("spec_digest", "abc"), ("spec_digest", D + "\n"),
            ("spec_digest", "0" * 64), ("trade_date", "2026-13-01"), ("trade_date", "2026-12-07\n"),
            ("session_state", "open"), ("session_state", {}), ("session_state", ["regular"]),
            ("is_trading_day", "yes"), ("blocks_orders", None), ("open_utc", None),
            ("order_cutoff_utc", "2026-12-07T14:00:00Z"), ("close_utc", "2026-12-08T21:00:00Z"),
            ("calendar_version", ""), ("is_trading_day", False), ("coverage_end_date", "2026-12-06"),
            ("coverage_start_date", "2026-12-08"), ("coverage_end_date", None))]
        cases.append(("closed_day_with_times", edited("2026-12-05", open_utc="2026-12-05T14:30:00.000Z")))
        cases.append(("closed_day_not_blocking", edited("2026-12-05", blocks_orders=False)))
        cases.append(("not_a_mapping", ["2026-12-07"]))
        for label, rec in cases:
            with self.subTest(label=label):
                with self.assertRaises(GateInputError):
                    validate_session(rec, D)
        for trusted in ("0" * 64, None, "abc", D + "\n"):
            with self.subTest(trusted=trusted):
                with self.assertRaises(GateInputError):
                    validate_session(DOC["sessions"]["2026-12-07"], trusted)

    def test_malformed_timestamps_fail_closed(self):
        for ts in ("2026-12-07T17:00:00+00:99", "2026-12-07T17:00:00+24:00", "2026-12-07T17:00:00", "2026-12-07 17:00:00Z",
                   "2026-12-07T17:00Z", "not-a-time", None, "", "0001-01-01T00:00:00Z", "9999-12-31T23:59:59-05:00",
                   "0001-01-01T00:00:00+05:00", "2026-12-07T17:00:00Z\n"):
            with self.subTest(ts=ts):
                d = gate(ts)
                self.assertFalse(d["orders_allowed"])
                self.assertIsNone(d["engine_inputs"]["session_calendar_status"])

    def test_successor_scan_stops_at_max_date(self):
        self.assertIsNone(fuse_gate._successor_session(CAL, date.max))
        self.assertIsNone(fuse_gate._next_calendar_day(date.max))

    def test_decision_does_not_mutate_calendar(self):
        before = CAL.session(date(2026, 12, 7))
        d = gate("2026-12-07T15:00:00Z")
        d["engine_inputs"]["session_time"] = "tampered"
        self.assertEqual(CAL.session(date(2026, 12, 7)), before)
        record = CAL.session(date(2026, 12, 7))
        record["blocks_orders"] = True
        self.assertFalse(CAL.session(date(2026, 12, 7))["blocks_orders"])


class TestEngineAgreement(unittest.TestCase):
    """Gate results drive the pinned engine, through evaluate(), to the expected verdicts."""

    @classmethod
    def setUpClass(cls):
        cls.normal_vi = json.loads((repo_root / "goldens" / "scenarios.json").read_text(encoding="utf-8"))[
            "scenarios"]["normal"]["inputs"]["validated_inputs"]
        # The spread-width threshold is an unresolved spec parameter; supply it explicitly
        # (as the other engine tests do) so V7 isolates the session check.
        cls.normal_vi["v7_spread_width"] = 0.02

    def _run(self, ts, exchange="open", calendar=CAL, vi=None):
        inputs, decision = gate_engine_inputs(copy.deepcopy(vi if vi is not None else self.normal_vi), ts, calendar, exchange)
        # Evaluate at the gate's own instant and New York session date.
        session = decision["trade_date"] or ts[:10]
        rows, _, _ = engine.evaluate(
            "fuse-eval-spec/v1", "test-hash", "registered_policy_hash_v1",
            session, ts, "shadow", inputs, {}, [])
        return rows, decision, inputs

    def test_rows_trip_independently_as_expected(self):
        # (ts, exchange, expect V7 trip, expect O2 trip)
        probes = [
            ("2026-12-07T15:00:00Z", "open", False, False),    # core session
            ("2026-12-07T21:30:00Z", "open", True, False),     # after hours: V7 blocks, day still a trading day
            ("2026-12-08T02:30:00Z", "open", True, False),     # 23/5 overnight
            ("2026-12-07T12:00:00Z", "open", True, False),     # pre-market
            ("2026-12-24T17:00:00Z", "open", False, False),    # half day before 13:00 ET
            ("2026-12-24T18:30:00Z", "open", True, True),      # half day past cutoff: O2 trips too
            ("2026-12-25T15:00:00Z", "holiday", True, True),
            ("2026-12-07T15:00:00Z", "closed", True, True),    # venue veto on a scheduled day
            ("2026-12-07T15:00:00Z", None, True, True),
            ("2027-01-04T15:00:00Z", "open", True, True),      # outside pinned coverage
        ]
        for ts, exchange, v7, o2 in probes:
            with self.subTest(ts=ts, exchange=exchange):
                rows, d, _ = self._run(ts, exchange)
                self.assertEqual(rows["V7"]["would_have_tripped"], v7, "V7")
                self.assertEqual(rows["O2"]["would_have_tripped"], o2, "O2")
                self.assertEqual(d["orders_allowed"], not (v7 or o2))

    def test_end_of_day_evaluation_still_runs_daily_breakers(self):
        # Codex P1 (round 5): the order cutoff must not mark the trading day closed for V1 and friends.
        vi = copy.deepcopy(self.normal_vi)
        sym = next(iter(vi["funds"]))
        vi["funds"][sym]["fund_return"] = 0.25  # far outside the fund's tracking tolerance
        before_close, _, _ = self._run("2026-12-07T20:59:59Z", vi=vi)
        at_close, d, inputs = self._run("2026-12-07T21:00:00Z", vi=vi)
        self.assertTrue(before_close["V1"]["would_have_tripped"])
        self.assertEqual(at_close["V1"]["would_have_tripped"], before_close["V1"]["would_have_tripped"])
        self.assertEqual(at_close["V1"]["state"], before_close["V1"]["state"])
        self.assertEqual(inputs["session_calendar_status"], "open")
        self.assertFalse(d["orders_allowed"])
        self.assertTrue(at_close["V7"]["would_have_tripped"])

    def test_stale_regular_tokens_in_every_v7_source_are_overwritten(self):
        vi = copy.deepcopy(self.normal_vi)
        quote = {"quote_staleness": 0.05, "spread_width": 0.0001, "trading_pause": False, "session_time": "regular"}
        for sym in vi["funds"]:
            vi["funds"][sym]["session_time"] = "regular"
        vi["quotes"] = {sym: dict(quote) for sym in vi["funds"]}
        vi["symbols"] = {sym: dict(quote) for sym in vi["funds"]}
        rows, _, applied = self._run("2026-12-07T22:00:00Z", vi=vi)
        for source in ("funds", "quotes", "symbols"):
            for sym, entry in applied[source].items():
                with self.subTest(source=source, sym=sym):
                    self.assertEqual(entry["session_time"], "outside_regular")
        self.assertTrue(rows["V7"]["would_have_tripped"])
        self.assertEqual(vi["funds"][next(iter(vi["funds"]))]["session_time"], "regular", "input not mutated")

    def test_only_the_loader_built_calendar_is_accepted(self):
        # Codex P2 (round 5): a subclass cannot stand in for the pinned calendar.
        with self.assertRaises(TypeError):
            type("Fake", (fuse_gate.TrustedCalendar,), {})
        class Lookalike:
            versions = ("csa22-v2",)
            def session(self, day):
                return CAL.session(day)
        rows, d, inputs = self._run("2026-12-07T15:00:00Z", calendar=Lookalike())
        self.assertEqual(d["reason"], "calendar_untrusted")
        self.assertIsNone(inputs["session_calendar_status"])
        self.assertTrue(rows["V7"]["would_have_tripped"] and rows["O2"]["would_have_tripped"])


if __name__ == "__main__":
    unittest.main()
