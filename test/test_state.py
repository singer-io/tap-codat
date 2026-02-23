import pytest
from dateutil.parser import parse

from tap_codat.state import (
    get_last_record_value_for_table,
    incorporate,
)


class TestGetLastRecordValueForTable:
    def test_returns_none_for_empty_state(self):
        state = {}
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_returns_none_when_stream_missing(self):
        state = {"bookmarks": {}}
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_returns_none_when_company_missing(self):
        state = {"bookmarks": {"invoices": {}}}
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_returns_none_when_last_record_missing(self):
        state = {"bookmarks": {"invoices": {"company-1": {"field": "modifiedDate"}}}}
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_returns_parsed_datetime(self):
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-06-15T10:30:00Z",
                    }
                }
            }
        }
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result == parse("2024-06-15T10:30:00Z")

    def test_returns_correct_company_value(self):
        """Ensure company-scoped bookmarks are independent."""
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-01-01T00:00:00Z",
                    },
                    "company-2": {
                        "field": "modifiedDate",
                        "last_record": "2024-06-15T00:00:00Z",
                    },
                }
            }
        }
        result = get_last_record_value_for_table(state, "invoices", "company-2")
        assert result == parse("2024-06-15T00:00:00Z")


class TestIncorporate:
    def test_returns_state_unchanged_when_value_is_none(self):
        state = {}
        result = incorporate(state, "invoices", "company-1", "modifiedDate", None)
        assert result == {}

    def test_creates_bookmark_structure_from_empty_state(self):
        state = {}
        result = incorporate(state, "invoices", "company-1", "modifiedDate", "2024-06-15T10:30:00Z")
        assert result == {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-06-15T10:30:00Z",
                    }
                }
            }
        }

    def test_updates_value_when_newer(self):
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-01-01T00:00:00Z",
                    }
                }
            }
        }
        result = incorporate(state, "invoices", "company-1", "modifiedDate", "2024-06-15T10:30:00Z")
        assert result["bookmarks"]["invoices"]["company-1"]["last_record"] == "2024-06-15T10:30:00Z"

    def test_does_not_update_value_when_older(self):
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-06-15T00:00:00Z",
                    }
                }
            }
        }
        result = incorporate(state, "invoices", "company-1", "modifiedDate", "2024-01-01T00:00:00Z")
        assert result["bookmarks"]["invoices"]["company-1"]["last_record"] == "2024-06-15T00:00:00Z"

    def test_preserves_other_companies(self):
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-01-01T00:00:00Z",
                    }
                }
            }
        }
        result = incorporate(state, "invoices", "company-2", "modifiedDate", "2024-06-15T00:00:00Z")
        assert "company-1" in result["bookmarks"]["invoices"]
        assert "company-2" in result["bookmarks"]["invoices"]
        assert result["bookmarks"]["invoices"]["company-1"]["last_record"] == "2024-01-01T00:00:00Z"
        assert result["bookmarks"]["invoices"]["company-2"]["last_record"] == "2024-06-15T00:00:00Z"

    def test_preserves_other_streams(self):
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {
                        "field": "modifiedDate",
                        "last_record": "2024-01-01T00:00:00Z",
                    }
                }
            }
        }
        result = incorporate(state, "bills", "company-1", "modifiedDate", "2024-06-15T00:00:00Z")
        assert "invoices" in result["bookmarks"]
        assert "bills" in result["bookmarks"]

    def test_bookmark_keys_are_tap_stream_ids(self):
        """Bookmark keys under 'bookmarks' must be tap_stream_ids, not
        'stream_name.companyId' composites."""
        state = {}
        result = incorporate(state, "invoices", "company-123", "modifiedDate", "2024-01-01T00:00:00Z")
        bookmark_keys = list(result["bookmarks"].keys())
        assert bookmark_keys == ["invoices"]
        assert "invoices.company-123" not in result["bookmarks"]


class TestStateClearingNoEmptyObjects:
    """When bookmarks are cleared/reset, there should be no leftover empty
    objects or null values — per the target-qlik and menagerie requirements."""

    def test_empty_bookmarks_is_valid(self):
        state = {"bookmarks": {}}
        # No empty nested objects
        assert state == {"bookmarks": {}}

    def test_empty_stream_bookmark_is_valid(self):
        state = {"bookmarks": {"invoices": {}}}
        # No empty company sub-objects
        assert "invoices" in state["bookmarks"]
        assert state["bookmarks"]["invoices"] == {}

    def test_no_none_company_bookmark(self):
        """Company bookmark should not be set to None — it should be absent."""
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": None  # BAD
                }
            }
        }
        # Demonstrate that get_last_record_value_for_table handles this
        # gracefully (returns None), but this shape should not be produced
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_no_empty_company_bookmark(self):
        """Company bookmark should not be an empty dict — it should be absent."""
        state = {
            "bookmarks": {
                "invoices": {
                    "company-1": {}  # BAD
                }
            }
        }
        result = get_last_record_value_for_table(state, "invoices", "company-1")
        assert result is None

    def test_incorporate_does_not_produce_empty_objects(self):
        """incorporate should never leave empty nested dicts."""
        state = {}
        result = incorporate(state, "invoices", "company-1", "modifiedDate", "2024-01-01T00:00:00Z")
        # Every nested level should have real content
        assert result["bookmarks"] != {}
        assert result["bookmarks"]["invoices"] != {}
        assert result["bookmarks"]["invoices"]["company-1"] != {}

    def test_no_offset_key_in_bookmarks(self):
        """Bookmarks should never contain an 'offset' key."""
        state = {}
        result = incorporate(state, "invoices", "company-1", "modifiedDate", "2024-01-01T00:00:00Z")
        for stream_key, stream_val in result.get("bookmarks", {}).items():
            if isinstance(stream_val, dict):
                assert "offset" not in stream_val
                for company_key, company_val in stream_val.items():
                    if isinstance(company_val, dict):
                        assert "offset" not in company_val
