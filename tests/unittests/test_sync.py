"""Unit tests for tap_codat sync logic — Context, capture_state,
Stream.format_response, stream-level sync, and the main sync() function."""

import json
import os
import unittest
from unittest.mock import MagicMock, patch

from singer import metadata

import tap_codat
from tap_codat.context import Context
from tap_codat.http import Client
from tap_codat import streams as streams_
from tap_codat.streams import (
    capture_state,
    Stream,
    Companies,
    Basic,
    Paginated,
    Financials,
    Events,
    BankAccounts,
    BankStatementLines,
    BankAccountTransactions,
    flatten_report,
    flatten_balance_sheets,
    flatten_profit_and_loss,
    trunc_payment_allocation_notes,
    PAGE_SIZE,
)

try:
    from ..mockedtests.base import CodatBaseTest
except ImportError:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "mockedtests"))
    from base import CodatBaseTest


# ---------------------------------------------------------------------------
# Context
# ---------------------------------------------------------------------------

class TestContextInit(unittest.TestCase):

    def test_init_sets_config_and_state(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {"bookmarks": {}})
        self.assertEqual(ctx.config["api_key"], "k")
        self.assertEqual(ctx.state, {"bookmarks": {}})

    def test_init_creates_client(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        self.assertIsInstance(ctx.client, Client)

    def test_init_cache_empty(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        self.assertEqual(ctx.cache, {})

    def test_catalog_is_none_initially(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        self.assertIsNone(ctx.catalog)
        self.assertIsNone(ctx.selected_stream_ids)
        self.assertIsNone(ctx.schema_dt_paths)


class TestContextCatalogSetter(CodatBaseTest, unittest.TestCase):

    def test_sets_selected_stream_ids(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies", "accounts"])
        ctx.catalog = catalog
        self.assertIn("companies", ctx.selected_stream_ids)
        self.assertIn("accounts", ctx.selected_stream_ids)
        self.assertNotIn("invoices", ctx.selected_stream_ids)

    def test_sets_all_stream_ids_when_all_selected(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        self.assertTrue(len(ctx.selected_stream_ids) > 10)

    def test_sets_schema_dt_paths(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        self.assertIsNotNone(ctx.schema_dt_paths)
        self.assertIn("companies", ctx.schema_dt_paths)
        self.assertIsInstance(ctx.schema_dt_paths["companies"], list)

    def test_schema_dt_paths_for_all_streams(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        for entry in catalog.streams:
            self.assertIn(entry.tap_stream_id, ctx.schema_dt_paths)


class TestContextBookmarks(unittest.TestCase):

    def test_get_bookmark_returns_none_for_missing(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        result = ctx.get_bookmark(("companies", "last_record"))
        self.assertIsNone(result)

    def test_set_and_get_bookmark(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        ctx.set_bookmark(("companies", "last_record"), "2024-01-01T00:00:00Z")
        result = ctx.get_bookmark(("companies", "last_record"))
        self.assertEqual(result, "2024-01-01T00:00:00Z")

    def test_update_start_date_bookmark_uses_config(self):
        ctx = Context({"api_key": "k", "uat_urls": "false", "start_date": "2023-01-01"}, {})
        val = ctx.update_start_date_bookmark(("stream", "last_record"))
        self.assertEqual(val, "2023-01-01")

    def test_update_start_date_bookmark_uses_existing(self):
        ctx = Context({"api_key": "k", "uat_urls": "false", "start_date": "2023-01-01"}, {})
        ctx.set_bookmark(("stream", "last_record"), "2024-06-01")
        val = ctx.update_start_date_bookmark(("stream", "last_record"))
        self.assertEqual(val, "2024-06-01")


class TestContextWriteState(unittest.TestCase):

    @patch("tap_codat.context.singer.write_state")
    def test_write_state_calls_singer(self, mock_write):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {"bookmarks": {}})
        ctx.write_state()
        mock_write.assert_called_once_with({"bookmarks": {}})


class TestContextDumpLogs(unittest.TestCase):

    def test_dump_logs_clears_client_logs(self):
        ctx = Context({"api_key": "k", "uat_urls": "false"}, {})
        ctx.client.logs = [{"test": True}]
        ctx.dump_logs()
        self.assertEqual(ctx.client.logs, [])


# ---------------------------------------------------------------------------
# capture_state
# ---------------------------------------------------------------------------

class TestCaptureState(CodatBaseTest, unittest.TestCase):

    def test_get_max_returns_start_date_when_no_state(self):
        ctx = self._create_context()
        ctx.state = {}
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            result = sync.get_max()
        self.assertEqual(result, self.default_config["start_date"])

    def test_get_max_returns_bookmark_when_state_exists(self):
        ctx = self._create_context(state={"bookmarks": {
            "accounts": {"comp-001": {"field": "modifiedDate", "last_record": "2024-06-01T00:00:00Z"}}
        }})
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            result = sync.get_max()
        self.assertIn("2024-06-01", result)

    def test_update_tracks_max_value(self):
        ctx = self._create_context()
        ctx.state = {}
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            sync.update([
                {"modifiedDate": "2024-01-01T00:00:00Z"},
                {"modifiedDate": "2024-06-01T00:00:00Z"},
                {"modifiedDate": "2024-03-01T00:00:00Z"},
            ])
            self.assertEqual(sync.max, "2024-06-01T00:00:00Z")

    def test_update_ignores_records_without_field(self):
        ctx = self._create_context()
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            sync.update([{"name": "test"}])
            self.assertIsNone(sync.max)

    def test_update_noop_when_field_is_none(self):
        ctx = self._create_context()
        with capture_state(ctx, "companies", None, "comp-001") as sync:
            sync.update([{"modifiedDate": "2024-01-01T00:00:00Z"}])
            self.assertIsNone(sync.max)

    @patch("tap_codat.streams.save_state")
    def test_exit_saves_state_when_max_set(self, mock_save):
        ctx = self._create_context()
        ctx.state = {}
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            sync.update([{"modifiedDate": "2024-06-01T00:00:00Z"}])
        mock_save.assert_called()

    @patch("tap_codat.streams.save_state")
    def test_exit_does_not_save_when_field_none(self, mock_save):
        ctx = self._create_context()
        with capture_state(ctx, "companies", None, "comp-001") as sync:
            pass
        mock_save.assert_not_called()

    @patch("tap_codat.streams.save_state")
    def test_exit_does_not_save_when_max_is_none(self, mock_save):
        ctx = self._create_context()
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            pass
        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# Stream.format_response
# ---------------------------------------------------------------------------

class TestStreamFormatResponse(unittest.TestCase):

    def test_collection_with_key(self):
        stream = Paginated("accounts", ["id", "companyId"],
                           "/test", collection_key="results")
        company = {"id": "c1"}
        records = stream.format_response({"results": [{"id": "a1"}]}, company)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyId"], "c1")

    def test_collection_with_key_empty(self):
        stream = Paginated("accounts", ["id", "companyId"],
                           "/test", collection_key="results")
        records = stream.format_response({"results": []}, {"id": "c1"})
        self.assertEqual(records, [])

    def test_collection_with_key_none_response(self):
        stream = Paginated("accounts", ["id", "companyId"],
                           "/test", collection_key="results")
        records = stream.format_response(None, {"id": "c1"})
        self.assertEqual(records, [])

    def test_collection_without_key(self):
        stream = Basic("bank_statements", ["accountName", "companyId"],
                       "/test")
        records = stream.format_response([{"accountName": "Checking"}], {"id": "c1"})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyId"], "c1")

    def test_collection_without_key_none(self):
        stream = Basic("bank_statements", ["accountName", "companyId"],
                       "/test")
        records = stream.format_response(None, {"id": "c1"})
        self.assertEqual(records, [])

    def test_non_collection_single_object(self):
        stream = Basic("company_info", ["companyId"], "/test",
                       returns_collection=False)
        records = stream.format_response({"companyName": "Corp"}, {"id": "c1"})
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyName"], "Corp")
        self.assertEqual(records[0]["companyId"], "c1")

    def test_non_collection_none(self):
        stream = Basic("company_info", ["companyId"], "/test",
                       returns_collection=False)
        records = stream.format_response(None, {"id": "c1"})
        self.assertEqual(records, [])

    def test_non_collection_list_input(self):
        stream = Basic("connections", ["id", "companyId"], "/test",
                       returns_collection=False)
        records = stream.format_response(
            [{"id": "conn-1"}, {"id": "conn-2"}], {"id": "c1"})
        self.assertEqual(len(records), 2)

    def test_extras_added(self):
        stream = Paginated("bank_accounts", ["accountName", "companyId"],
                           "/test", collection_key="results")
        records = stream.format_response(
            {"results": [{"accountName": "Checking"}]},
            {"id": "c1"},
            {"connectionId": "conn-1"},
        )
        self.assertEqual(records[0]["connectionId"], "conn-1")

    def test_custom_formatter_applied(self):
        formatter = lambda records: [dict(r, formatted=True) for r in records]
        stream = Stream("test", ["id"], "/test", collection_key="results",
                        custom_formatter=formatter)
        records = stream.format_response(
            {"results": [{"id": "1"}]}, {"id": "c1"})
        self.assertTrue(records[0]["formatted"])

    def test_multiple_records(self):
        stream = Paginated("accounts", ["id", "companyId"],
                           "/test", collection_key="results")
        records = stream.format_response(
            {"results": [{"id": "1"}, {"id": "2"}, {"id": "3"}]},
            {"id": "c1"})
        self.assertEqual(len(records), 3)
        for r in records:
            self.assertEqual(r["companyId"], "c1")


# ---------------------------------------------------------------------------
# flatten_report
# ---------------------------------------------------------------------------

class TestFlattenReport(unittest.TestCase):

    def test_flat_item(self):
        result = flatten_report({"name": "Assets", "value": 100, "items": []})
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Assets")
        self.assertEqual(result[0]["value"], 100)
        self.assertEqual(result[0]["name_0"], "Assets")

    def test_nested_one_level(self):
        item = {"name": "A", "value": 10, "items": [
            {"name": "B", "value": 5, "items": []}
        ]}
        result = flatten_report(item)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["name"], "A")
        self.assertEqual(result[1]["name"], "B")
        self.assertEqual(result[1]["name_0"], "A")
        self.assertEqual(result[1]["name_1"], "B")

    def test_nested_two_levels(self):
        item = {"name": "A", "value": 10, "items": [
            {"name": "B", "value": 5, "items": [
                {"name": "C", "value": 3, "items": []}
            ]}
        ]}
        result = flatten_report(item)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[2]["name_0"], "A")
        self.assertEqual(result[2]["name_1"], "B")
        self.assertEqual(result[2]["name_2"], "C")

    def test_multiple_children(self):
        item = {"name": "Root", "value": 100, "items": [
            {"name": "Child1", "value": 60, "items": []},
            {"name": "Child2", "value": 40, "items": []},
        ]}
        result = flatten_report(item)
        self.assertEqual(len(result), 3)
        names = [r["name"] for r in result]
        self.assertEqual(names, ["Root", "Child1", "Child2"])

    def test_accountId_present(self):
        result = flatten_report({"name": "X", "value": 1, "accountId": "acct-001"})
        self.assertEqual(result[0]["accountId"], "acct-001")

    def test_accountId_none_when_missing(self):
        result = flatten_report({"name": "X", "value": 1})
        self.assertIsNone(result[0]["accountId"])

    def test_no_items_key(self):
        result = flatten_report({"name": "X", "value": 1})
        self.assertEqual(len(result), 1)


# ---------------------------------------------------------------------------
# flatten_balance_sheets
# ---------------------------------------------------------------------------

class TestFlattenBalanceSheets(unittest.TestCase):

    def test_flattens_all_sections(self):
        bs = [{"reports": [{
            "assets": {"name": "A", "value": 100, "items": []},
            "liabilities": {"name": "L", "value": 50, "items": []},
            "equity": {"name": "E", "value": 50, "items": []},
        }]}]
        result = flatten_balance_sheets(bs)
        report = result[0]["reports"][0]
        for key in ["assets", "liabilities", "equity"]:
            self.assertIsInstance(report[key], list)
            self.assertEqual(report[key][0]["name"], {"assets": "A", "liabilities": "L", "equity": "E"}[key])

    def test_multiple_reports(self):
        bs = [{"reports": [
            {"assets": {"name": "A1", "value": 100, "items": []},
             "liabilities": {"name": "L1", "value": 50, "items": []},
             "equity": {"name": "E1", "value": 50, "items": []}},
            {"assets": {"name": "A2", "value": 200, "items": []},
             "liabilities": {"name": "L2", "value": 100, "items": []},
             "equity": {"name": "E2", "value": 100, "items": []}},
        ]}]
        result = flatten_balance_sheets(bs)
        self.assertEqual(len(result[0]["reports"]), 2)


# ---------------------------------------------------------------------------
# flatten_profit_and_loss
# ---------------------------------------------------------------------------

class TestFlattenProfitAndLoss(unittest.TestCase):

    def test_flattens_all_keys(self):
        pnl = [{"reports": [{
            "income": {"name": "I", "value": 1000, "items": []},
            "costOfSales": {"name": "C", "value": 300, "items": []},
            "expenses": {"name": "E", "value": 200, "items": []},
            "otherIncome": {"name": "OI", "value": 50, "items": []},
            "otherExpenses": {"name": "OE", "value": 10, "items": []},
        }]}]
        result = flatten_profit_and_loss(pnl)
        report = result[0]["reports"][0]
        for key in ["income", "costOfSales", "expenses", "otherIncome", "otherExpenses"]:
            self.assertIsInstance(report[key], list)
            self.assertTrue(len(report[key]) > 0)


# ---------------------------------------------------------------------------
# trunc_payment_allocation_notes
# ---------------------------------------------------------------------------

class TestTruncPaymentAllocationNotes(unittest.TestCase):

    def test_truncates_long_note(self):
        invoices = [{"paymentAllocations": [{"note": "x" * 2000}]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(len(result[0]["paymentAllocations"][0]["note"]), 1024)

    def test_preserves_short_note(self):
        invoices = [{"paymentAllocations": [{"note": "short"}]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["paymentAllocations"][0]["note"], "short")

    def test_preserves_exactly_1024(self):
        invoices = [{"paymentAllocations": [{"note": "x" * 1024}]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(len(result[0]["paymentAllocations"][0]["note"]), 1024)

    def test_no_payment_allocations(self):
        invoices = [{"id": "inv-001"}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["id"], "inv-001")

    def test_empty_allocations_list(self):
        invoices = [{"paymentAllocations": []}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["paymentAllocations"], [])

    def test_non_string_note(self):
        invoices = [{"paymentAllocations": [{"note": 12345}]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["paymentAllocations"][0]["note"], 12345)

    def test_none_note(self):
        invoices = [{"paymentAllocations": [{"note": None}]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertIsNone(result[0]["paymentAllocations"][0]["note"])

    def test_multiple_allocations(self):
        invoices = [{"paymentAllocations": [
            {"note": "x" * 2000},
            {"note": "short"},
            {"note": "y" * 5000},
        ]}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(len(result[0]["paymentAllocations"][0]["note"]), 1024)
        self.assertEqual(result[0]["paymentAllocations"][1]["note"], "short")
        self.assertEqual(len(result[0]["paymentAllocations"][2]["note"]), 1024)

    def test_multiple_invoices(self):
        invoices = [
            {"paymentAllocations": [{"note": "a" * 2000}]},
            {"paymentAllocations": [{"note": "b" * 2000}]},
        ]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(len(result[0]["paymentAllocations"][0]["note"]), 1024)
        self.assertEqual(len(result[1]["paymentAllocations"][0]["note"]), 1024)


# ---------------------------------------------------------------------------
# Stream sync — Companies
# ---------------------------------------------------------------------------

class TestCompaniesSync(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_writes_cached_companies(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        streams_.companies.sync(ctx)
        mock_write.assert_called()
        self.assertEqual(mock_write.call_args[0][0], "companies")
        records = mock_write.call_args[0][1]
        self.assertEqual(len(records), len(self.MOCK_COMPANIES))

    @patch("tap_codat.streams.singer.write_records")
    def test_company_records_have_id(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        streams_.companies.sync(ctx)
        for record in mock_write.call_args[0][1]:
            self.assertIn("id", record)


class TestCompaniesFetchIntoCache(CodatBaseTest, unittest.TestCase):

    def test_populates_cache(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        self.assertIn("companies", ctx.cache)
        self.assertEqual(len(ctx.cache["companies"]), len(self.MOCK_COMPANIES))

    def test_cache_records_have_id(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        for company in ctx.cache["companies"]:
            self.assertIn("id", company)


# ---------------------------------------------------------------------------
# Stream sync — Basic (accounts)
# ---------------------------------------------------------------------------

class TestBasicSync(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_accounts_sync_writes_records(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies", "accounts"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        acct_stream = next(s for s in streams_.all_streams if s.tap_stream_id == "accounts")
        acct_stream.sync(ctx)
        mock_write.assert_called()
        self.assertEqual(mock_write.call_args[0][0], "accounts")

    @patch("tap_codat.streams.singer.write_records")
    def test_accounts_records_have_company_id(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies", "accounts"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        acct_stream = next(s for s in streams_.all_streams if s.tap_stream_id == "accounts")
        acct_stream.sync(ctx)
        for record in mock_write.call_args[0][1]:
            self.assertEqual(record["companyId"], "comp-001")


# ---------------------------------------------------------------------------
# Stream sync — Paginated (invoices)
# ---------------------------------------------------------------------------

class TestPaginatedSync(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_invoices_sync_writes_records(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=["companies", "invoices"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        inv_stream = next(s for s in streams_.all_streams if s.tap_stream_id == "invoices")
        inv_stream.sync(ctx)
        mock_write.assert_called()
        self.assertEqual(mock_write.call_args[0][0], "invoices")


class TestPaginatedGetParams(unittest.TestCase):

    def test_includes_page_and_size(self):
        stream = Paginated("accounts", ["id"], "/test",
                           collection_key="results", state_filter="modifiedDate")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = None
        params = stream.get_params(ctx, sync, 1)
        self.assertEqual(params["page"], 1)
        self.assertEqual(params["pageSize"], PAGE_SIZE)
        self.assertEqual(params["orderBy"], "modifiedDate")

    def test_includes_incremental_filter(self):
        stream = Paginated("accounts", ["id"], "/test",
                           collection_key="results", state_filter="modifiedDate")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = "2024-01-01T00:00:00Z"
        params = stream.get_params(ctx, sync, 2)
        self.assertEqual(params["page"], 2)
        self.assertIn("query", params)
        self.assertIn("modifiedDate", params["query"])


# ---------------------------------------------------------------------------
# Stream sync — Events
# ---------------------------------------------------------------------------

class TestEventsGetParams(unittest.TestCase):

    def test_includes_from_date(self):
        stream = Events("events", ["eventTimeUtc", "companyId"],
                        "/test", collection_key="data")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = "2024-06-01T00:00:00Z"
        params = stream.get_params(ctx, sync)
        self.assertEqual(params["fromDate"], "2024-06-01T00:00:00Z")

    def test_empty_params_when_no_max(self):
        stream = Events("events", ["eventTimeUtc", "companyId"],
                        "/test", collection_key="data")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = None
        params = stream.get_params(ctx, sync)
        self.assertEqual(params, {})


# ---------------------------------------------------------------------------
# Stream sync — Financials (company_info)
# ---------------------------------------------------------------------------

class TestFinancialsSync(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_balance_sheets_sync(self, mock_write):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(
            stream_names=["companies", "balance_sheets"])
        ctx.catalog = catalog
        streams_.companies.fetch_into_cache(ctx)
        bs_stream = next(s for s in streams_.all_streams
                         if s.tap_stream_id == "balance_sheets")
        bs_stream.sync(ctx)
        mock_write.assert_called()
        self.assertEqual(mock_write.call_args[0][0], "balance_sheets")


# ---------------------------------------------------------------------------
# Basic.get_incremental_filter
# ---------------------------------------------------------------------------

class TestGetIncrementalFilter(unittest.TestCase):

    def test_returns_query_when_state_filter_set(self):
        stream = Basic("accounts", ["id"], "/test", state_filter="modifiedDate")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = "2024-01-01T00:00:00Z"
        result = stream.get_incremental_filter(ctx, sync)
        self.assertIn("query", result)
        self.assertIn("modifiedDate>2024-01-01T00:00:00Z", result["query"])

    def test_returns_empty_when_no_state_filter(self):
        stream = Basic("company_info", ["companyId"], "/test",
                       returns_collection=False)
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = "2024-01-01T00:00:00Z"
        result = stream.get_incremental_filter(ctx, sync)
        self.assertEqual(result, {})

    def test_returns_empty_when_no_max(self):
        stream = Basic("accounts", ["id"], "/test", state_filter="modifiedDate")
        ctx = MagicMock()
        sync = MagicMock()
        sync.get_max.return_value = None
        result = stream.get_incremental_filter(ctx, sync)
        self.assertEqual(result, {})


# ---------------------------------------------------------------------------
# Main sync() function
# ---------------------------------------------------------------------------

class TestMainSync(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_sync_clears_currently_syncing(
        self, mock_ctx_ws, mock_ws, mock_stream_ws, mock_wr,
    ):
        # Exclude financials streams whose custom_formatter mutates the mock
        # data in-place; those are tested separately in TestFinancialsSync.
        exclude = {"balance_sheets", "profit_and_loss"}
        names = [s.tap_stream_id for s in streams_.all_streams
                 if s.tap_stream_id not in exclude]
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=names)
        tap_codat.sync(ctx)
        self.assertIsNone(ctx.state.get("currently_syncing"))

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_sync_writes_records_for_selected_streams(
        self, mock_ctx_ws, mock_ws, mock_stream_ws, mock_wr,
    ):
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=["companies"])
        tap_codat.sync(ctx)
        written_streams = {c[0][0] for c in mock_wr.call_args_list}
        self.assertIn("companies", written_streams)
        self.assertNotIn("accounts", written_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_sync_writes_schemas_before_records(
        self, mock_ctx_ws, mock_ws, mock_stream_ws, mock_wr,
    ):
        call_order = []
        mock_ws.side_effect = lambda *a, **k: call_order.append(("schema", a[0]))
        mock_wr.side_effect = lambda *a, **k: call_order.append(("record", a[0]))

        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=["companies"])
        tap_codat.sync(ctx)

        schema_idx = next(i for i, (t, s) in enumerate(call_order)
                          if t == "schema" and s == "companies")
        record_idx = next(i for i, (t, s) in enumerate(call_order)
                          if t == "record" and s == "companies")
        self.assertLess(schema_idx, record_idx)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_sync_resumes_from_currently_syncing(
        self, mock_ctx_ws, mock_ws, mock_stream_ws, mock_wr,
    ):
        """When currently_syncing is set, sync resumes from that stream."""
        exclude = {"balance_sheets", "profit_and_loss"}
        names = [s.tap_stream_id for s in streams_.all_streams
                 if s.tap_stream_id not in exclude]
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=names)
        ctx.state["currently_syncing"] = "bills"
        tap_codat.sync(ctx)
        # Should still complete and clear currently_syncing
        self.assertIsNone(ctx.state.get("currently_syncing"))


# ---------------------------------------------------------------------------
# Stream write_records
# ---------------------------------------------------------------------------

class TestStreamWriteRecords(unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_write_records_calls_singer(self, mock_write):
        stream = Stream("test", ["id"], "/test")
        stream.write_records([{"id": "1"}, {"id": "2"}])
        mock_write.assert_called_once_with("test", [{"id": "1"}, {"id": "2"}])

    @patch("tap_codat.streams.singer.write_records")
    def test_write_records_empty(self, mock_write):
        stream = Stream("test", ["id"], "/test")
        stream.write_records([])
        mock_write.assert_called_once_with("test", [])

    @patch("tap_codat.streams.LOGGER.info")
    @patch("tap_codat.streams.singer.write_records")
    def test_write_records_logs_oversized_payload(self, mock_write, mock_log):
        stream = Stream("test", ["id"], "/test")
        huge = {"id": "r1", "payload": "x" * ((4 * 1024 * 1024) + 1)}
        stream.write_records([huge])
        mock_write.assert_called_once_with("test", [huge])
        self.assertTrue(
            any("I saw record that was" in str(call_) for call_ in mock_log.call_args_list)
        )


class TestStreamAdditionalProperties(unittest.TestCase):

    @patch("tap_codat.streams.LOGGER.info")
    @patch("tap_codat.streams.tform", side_effect=Exception("validation failed"))
    def test_log_additional_properties_on_transform_error(self, _mock_tform, mock_log):
        stream = Stream("accounts", ["id"], "/test")
        ctx = MagicMock()
        ctx.catalog.get_stream.return_value.schema.to_dict.return_value = {
            "type": "object",
            "properties": {},
        }
        stream.log_additional_properties(ctx, [{"id": "1"}])
        mock_log.assert_called_once()


class TestBankStatementLines(unittest.TestCase):

    def test_sync_children_pops_details_and_writes_lines(self):
        stream = BankStatementLines("bank_statement_lines", ["companyId"], None)
        company = {"id": "c1"}
        statements = [{"accountName": "A", "details": [{"amount": 1}, {"amount": 2}]}]

        with patch.object(stream, "write_records") as mock_write:
            stream.sync_children(MagicMock(), "/ignored", company, statements)

        self.assertNotIn("details", statements[0])
        written = mock_write.call_args[0][0]
        self.assertEqual(written[0]["companyId"], "c1")
        self.assertEqual(written[0]["accountName"], "A")
        self.assertEqual(written[0]["_lineIndex"], 0)


class TestBankAccountTransactions(unittest.TestCase):

    def test_sync_children_calls_sync_per_account(self):
        stream = BankAccountTransactions("bank_account_transactions", ["companyId"], "/{id}/transactions")
        with patch.object(stream, "sync_transactions_for_account") as mock_sync:
            stream.sync_children(MagicMock(), "/companies/c1/data/bankAccounts", {"id": "c1"}, [{"id": "a1"}, {"id": "a2"}])
        self.assertEqual(mock_sync.call_count, 2)

    def test_sync_transactions_returns_when_missing_id(self):
        stream = BankAccountTransactions("bank_account_transactions", ["companyId"], "/{id}/transactions")
        ctx = MagicMock()
        with patch.object(stream, "write_records") as mock_write:
            stream.sync_transactions_for_account(ctx, "/parent", {"id": "c1"}, {"name": "acct"})
        ctx.client.GET.assert_not_called()
        mock_write.assert_not_called()

    def test_sync_transactions_returns_when_response_none(self):
        stream = BankAccountTransactions("bank_account_transactions", ["companyId"], "/{id}/transactions")
        ctx = MagicMock()
        ctx.client.GET.return_value = None
        with patch.object(stream, "write_records") as mock_write:
            stream.sync_transactions_for_account(ctx, "/parent", {"id": "c1"}, {"id": "a1"})
        mock_write.assert_not_called()

    def test_sync_transactions_writes_enriched_records(self):
        stream = BankAccountTransactions("bank_account_transactions", ["companyId"], "/{id}/transactions")
        ctx = MagicMock()
        ctx.client.GET.return_value = [{"amount": 1}, {"amount": 2}]
        with patch.object(stream, "transform_dts", return_value=[{"amount": 1}, {"amount": 2}]):
            with patch.object(stream, "write_records") as mock_write:
                stream.sync_transactions_for_account(ctx, "/parent", {"id": "c1"}, {"id": "a1"})
        written = mock_write.call_args[0][0]
        self.assertEqual(written[0]["companyId"], "c1")
        self.assertEqual(written[0]["bankAccountId"], "a1")
        self.assertEqual(written[1]["_transactionIndex"], 1)


class TestPaginationBranches(unittest.TestCase):

    def test_paginated_sync_advances_page(self):
        stream = Paginated("accounts", ["id", "companyId"], "/companies/{companyId}/data/accounts", collection_key="results", state_filter="modifiedDate")
        ctx = MagicMock()
        company = {"id": "c1"}

        full_page = [{"id": str(i)} for i in range(PAGE_SIZE)]
        short_page = [{"id": "last"}]
        ctx.client.GET.side_effect = [
            {"results": full_page},
            {"results": short_page},
        ]

        with patch.object(stream, "transform_dts", side_effect=lambda _ctx, recs: recs):
            with patch.object(stream, "write_records"):
                stream.sync_for_company(ctx, company)

        first_params = ctx.client.GET.call_args_list[0][0][0]["params"]
        second_params = ctx.client.GET.call_args_list[1][0][0]["params"]
        self.assertEqual(first_params["page"], 1)
        self.assertEqual(second_params["page"], 2)

    def test_bank_accounts_skips_connection_without_id(self):
        stream = BankAccounts("bank_accounts", ["accountName", "companyId", "connectionId"], "/companies/{companyId}/connections/{connectionId}/data/bankAccounts", collection_key="results", state_filter="modifiedDate")
        ctx = MagicMock()
        company = {
            "id": "c1",
            "dataConnections": [{"id": None}, {"id": "conn-1"}],
        }
        ctx.client.GET.return_value = {"results": []}

        with patch.object(stream, "transform_dts", side_effect=lambda _ctx, recs: recs):
            with patch.object(stream, "write_records"):
                stream.sync_for_company(ctx, company)

        call_path = ctx.client.GET.call_args[0][0]["path"]
        self.assertIn("conn-1", call_path)

    def test_bank_accounts_advances_page(self):
        stream = BankAccounts("bank_accounts", ["accountName", "companyId", "connectionId"], "/companies/{companyId}/connections/{connectionId}/data/bankAccounts", collection_key="results", state_filter="modifiedDate")
        ctx = MagicMock()
        company = {"id": "c1", "dataConnections": [{"id": "conn-1"}]}
        ctx.client.GET.side_effect = [
            {"results": [{"accountName": str(i)} for i in range(PAGE_SIZE)]},
            {"results": [{"accountName": "last"}]},
        ]

        with patch.object(stream, "transform_dts", side_effect=lambda _ctx, recs: recs):
            with patch.object(stream, "write_records"):
                stream.sync_for_company(ctx, company)

        params1 = ctx.client.GET.call_args_list[0][0][0]["params"]
        params2 = ctx.client.GET.call_args_list[1][0][0]["params"]
        self.assertEqual(params1["page"], 1)
        self.assertEqual(params2["page"], 2)


if __name__ == "__main__":
    unittest.main()
