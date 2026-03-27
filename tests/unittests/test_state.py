"""Unit tests for tap_codat.state — get_last_record_value_for_table,
incorporate, save_state, and load_state."""

import json
import unittest
from unittest.mock import mock_open, patch

from tap_codat.state import (
    get_last_record_value_for_table,
    incorporate,
    load_state,
    save_state,
)


# ---------------------------------------------------------------------------
# get_last_record_value_for_table
# ---------------------------------------------------------------------------

class TestGetLastRecordValueForTable(unittest.TestCase):

    def test_no_bookmarks_returns_none(self):
        self.assertIsNone(get_last_record_value_for_table({}, "accounts.comp-001"))

    def test_empty_state_returns_none(self):
        self.assertIsNone(get_last_record_value_for_table({}, "companies"))

    def test_table_not_in_bookmarks_returns_none(self):
        state = {"bookmarks": {}}
        self.assertIsNone(get_last_record_value_for_table(state, "accounts.comp-001"))

    def test_last_record_is_none_returns_none(self):
        state = {"bookmarks": {"accounts.comp-001": {"last_record": None}}}
        self.assertIsNone(get_last_record_value_for_table(state, "accounts.comp-001"))

    def test_returns_datetime_when_present(self):
        state = {"bookmarks": {"accounts.comp-001": {
            "field": "modifiedDate",
            "last_record": "2024-06-15T10:00:00Z",
        }}}
        result = get_last_record_value_for_table(state, "accounts.comp-001")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)

    def test_returns_correct_time(self):
        state = {"bookmarks": {"invoices.c1": {
            "last_record": "2024-03-15T14:30:45Z",
        }}}
        result = get_last_record_value_for_table(state, "invoices.c1")
        self.assertEqual(result.hour, 14)
        self.assertEqual(result.minute, 30)

    def test_different_tables_return_different_values(self):
        state = {"bookmarks": {
            "accounts.c1": {"last_record": "2024-01-01T00:00:00Z"},
            "invoices.c1": {"last_record": "2024-06-01T00:00:00Z"},
        }}
        acct = get_last_record_value_for_table(state, "accounts.c1")
        inv = get_last_record_value_for_table(state, "invoices.c1")
        self.assertNotEqual(acct, inv)
        self.assertEqual(acct.month, 1)
        self.assertEqual(inv.month, 6)

    def test_does_not_mutate_state(self):
        state = {"bookmarks": {"t1": {"last_record": "2024-01-01T00:00:00Z"}}}
        original = json.dumps(state)
        get_last_record_value_for_table(state, "t1")
        self.assertEqual(json.dumps(state), original)


# ---------------------------------------------------------------------------
# incorporate
# ---------------------------------------------------------------------------

class TestIncorporate(unittest.TestCase):

    def test_value_none_returns_state_unchanged(self):
        state = {}
        result = incorporate(state, "accounts.c1", "modifiedDate", None)
        self.assertEqual(result, {})

    def test_creates_bookmark_when_none_exists(self):
        result = incorporate({}, "accounts.c1", "modifiedDate", "2024-03-15T10:00:00Z")
        self.assertIn("bookmarks", result)
        self.assertIn("accounts.c1", result["bookmarks"])
        self.assertEqual(result["bookmarks"]["accounts.c1"]["field"], "modifiedDate")
        self.assertEqual(result["bookmarks"]["accounts.c1"]["last_record"],
                         "2024-03-15T10:00:00Z")

    def test_updates_when_newer(self):
        state = {"bookmarks": {"t1": {"field": "f", "last_record": "2024-01-01T00:00:00Z"}}}
        result = incorporate(state, "t1", "f", "2024-06-15T10:00:00Z")
        self.assertEqual(result["bookmarks"]["t1"]["last_record"], "2024-06-15T10:00:00Z")

    def test_does_not_update_when_older(self):
        state = {"bookmarks": {"t1": {"field": "f", "last_record": "2024-06-15T10:00:00Z"}}}
        result = incorporate(state, "t1", "f", "2024-01-01T00:00:00Z")
        self.assertEqual(result["bookmarks"]["t1"]["last_record"], "2024-06-15T10:00:00Z")

    def test_does_not_mutate_original(self):
        state = {}
        result = incorporate(state, "t1", "f", "2024-01-01T00:00:00Z")
        self.assertNotIn("bookmarks", state)
        self.assertIn("bookmarks", result)

    def test_preserves_other_bookmarks(self):
        state = {"bookmarks": {"t1": {"field": "f", "last_record": "2024-01-01T00:00:00Z"}}}
        result = incorporate(state, "t2", "g", "2024-06-15T10:00:00Z")
        self.assertIn("t1", result["bookmarks"])
        self.assertIn("t2", result["bookmarks"])

    def test_sequential_incorporates(self):
        state = {}
        state = incorporate(state, "t1", "f", "2024-01-01T00:00:00Z")
        state = incorporate(state, "t1", "f", "2024-03-01T00:00:00Z")
        state = incorporate(state, "t1", "f", "2024-06-01T00:00:00Z")
        self.assertEqual(state["bookmarks"]["t1"]["last_record"], "2024-06-01T00:00:00Z")

    def test_incorporate_with_existing_bookmarks_on_new_table(self):
        state = {"bookmarks": {"t1": {"field": "f", "last_record": "2024-01-01T00:00:00Z"}}}
        result = incorporate(state, "t2", "g", "2024-05-01T00:00:00Z")
        self.assertEqual(result["bookmarks"]["t1"]["last_record"], "2024-01-01T00:00:00Z")
        self.assertEqual(result["bookmarks"]["t2"]["last_record"], "2024-05-01T00:00:00Z")


class TestIncorporateRoundTrip(unittest.TestCase):
    """Verify incorporate and get_last_record_value_for_table work together."""

    def test_write_then_read(self):
        state = incorporate({}, "accounts.c1", "modifiedDate", "2024-10-15T00:00:00Z")
        result = get_last_record_value_for_table(state, "accounts.c1")
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 10)

    def test_write_multiple_then_read_each(self):
        state = {}
        state = incorporate(state, "accounts.c1", "modifiedDate", "2024-01-01T00:00:00Z")
        state = incorporate(state, "invoices.c1", "modifiedDate", "2024-06-01T00:00:00Z")
        acct = get_last_record_value_for_table(state, "accounts.c1")
        inv = get_last_record_value_for_table(state, "invoices.c1")
        self.assertEqual(acct.month, 1)
        self.assertEqual(inv.month, 6)

    def test_overwrite_advances_bookmark(self):
        state = incorporate({}, "t1", "f", "2024-01-01T00:00:00Z")
        r1 = get_last_record_value_for_table(state, "t1")
        self.assertEqual(r1.month, 1)
        state = incorporate(state, "t1", "f", "2024-12-01T00:00:00Z")
        r2 = get_last_record_value_for_table(state, "t1")
        self.assertEqual(r2.month, 12)

    def test_unwritten_table_returns_none(self):
        state = incorporate({}, "t1", "f", "2024-01-01T00:00:00Z")
        result = get_last_record_value_for_table(state, "t2")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# save_state
# ---------------------------------------------------------------------------

class TestSaveState(unittest.TestCase):

    @patch("tap_codat.state.singer.write_state")
    def test_writes_nonempty_state(self, mock_write):
        state = {"bookmarks": {"t1": {"last_record": "2024-01-01T00:00:00Z"}}}
        save_state(state)
        mock_write.assert_called_once_with(state)

    @patch("tap_codat.state.singer.write_state")
    def test_does_not_write_empty_state(self, mock_write):
        save_state({})
        mock_write.assert_not_called()

    @patch("tap_codat.state.singer.write_state")
    def test_does_not_write_none(self, mock_write):
        save_state(None)
        mock_write.assert_not_called()

    @patch("tap_codat.state.singer.write_state")
    def test_writes_state_with_bookmarks(self, mock_write):
        state = {"bookmarks": {"a": {"last_record": "2024-01-01T00:00:00Z"}}}
        save_state(state)
        written = mock_write.call_args[0][0]
        self.assertIn("bookmarks", written)


# ---------------------------------------------------------------------------
# load_state
# ---------------------------------------------------------------------------

class TestLoadState(unittest.TestCase):

    def test_none_returns_empty_dict(self):
        self.assertEqual(load_state(None), {})

    def test_valid_json_returns_dict(self):
        state = {"bookmarks": {"t1": {"last_record": "2024-01-01T00:00:00Z"}}}
        m = mock_open(read_data=json.dumps(state))
        with patch("builtins.open", m):
            result = load_state("state.json")
        self.assertEqual(result, state)

    def test_invalid_json_raises_runtime_error(self):
        m = mock_open(read_data="{not valid json}")
        with patch("builtins.open", m):
            with self.assertRaises(RuntimeError):
                load_state("bad_state.json")

    def test_empty_json_object(self):
        m = mock_open(read_data="{}")
        with patch("builtins.open", m):
            result = load_state("empty_state.json")
        self.assertEqual(result, {})


if __name__ == "__main__":
    unittest.main()
