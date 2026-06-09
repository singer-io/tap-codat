"""Unit tests for tap_codat modules."""

import json
import os
import unittest
from io import StringIO
from unittest.mock import MagicMock, mock_open, patch

import tap_codat
from tap_codat.context import Context
from tap_codat.http import Client, RateLimitException
from tap_codat.state import (
    get_last_record_value_for_table,
    incorporate,
    load_state,
    save_state,
)
from tap_codat.streams import (
    capture_state,
    flatten_report,
    flatten_balance_sheets,
    flatten_profit_and_loss,
    trunc_payment_allocation_notes,
)
from tap_codat.transform import (
    DictKey,
    ListItems,
    find_dt_paths,
    safe_strftime,
    transform_dts,
)

try:
    from ..base import CodatBaseTest
except ImportError:
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from base import CodatBaseTest


# ---------------------------------------------------------------------------
# state.load_state
# ---------------------------------------------------------------------------

class TestLoadState(unittest.TestCase):

    def test_returns_empty_dict_when_filename_is_none(self):
        result = load_state(None)
        self.assertEqual(result, {})

    def test_returns_parsed_json_from_file(self):
        state = {'bookmarks': {'companies': {'last_record': '2024-01-01T00:00:00Z'}}}
        m = mock_open(read_data=json.dumps(state))
        with patch('builtins.open', m):
            result = load_state('state.json')
        self.assertEqual(result, state)

    def test_raises_runtime_error_on_invalid_json(self):
        m = mock_open(read_data='{not valid json}')
        with patch('builtins.open', m):
            with self.assertRaises(RuntimeError):
                load_state('bad_state.json')


# ---------------------------------------------------------------------------
# state.get_last_record_value_for_table
# ---------------------------------------------------------------------------

class TestGetLastRecordValueForTable(unittest.TestCase):

    def test_returns_none_when_no_bookmarks(self):
        state = {}
        result = get_last_record_value_for_table(state, 'companies', 'comp-001')
        self.assertIsNone(result)

    def test_returns_none_when_table_not_in_bookmarks(self):
        state = {'bookmarks': {}}
        result = get_last_record_value_for_table(state, 'accounts', 'comp-001')
        self.assertIsNone(result)

    def test_returns_none_when_last_record_is_none(self):
        state = {'bookmarks': {'accounts': {'comp-001': {'last_record': None}}}}
        result = get_last_record_value_for_table(state, 'accounts', 'comp-001')
        self.assertIsNone(result)

    def test_returns_datetime_when_bookmark_exists(self):
        state = {'bookmarks': {'accounts': {'comp-001': {
            'field': 'modifiedDate',
            'last_record': '2024-06-15T10:00:00Z',
        }}}}
        result = get_last_record_value_for_table(state, 'accounts', 'comp-001')
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2024)
        self.assertEqual(result.month, 6)
        self.assertEqual(result.day, 15)


# ---------------------------------------------------------------------------
# state.incorporate
# ---------------------------------------------------------------------------

class TestIncorporate(unittest.TestCase):

    def test_returns_state_unchanged_when_value_is_none(self):
        state = {}
        result = incorporate(state, 'accounts', 'comp-001', 'modifiedDate', None)
        self.assertEqual(result, {})

    def test_adds_bookmark_when_no_existing_bookmark(self):
        state = {}
        result = incorporate(state, 'accounts', 'comp-001', 'modifiedDate',
                             '2024-03-15T10:00:00Z')
        self.assertIn('bookmarks', result)
        self.assertIn('accounts', result['bookmarks'])
        self.assertIn('comp-001', result['bookmarks']['accounts'])
        self.assertEqual(result['bookmarks']['accounts']['comp-001']['field'],
                         'modifiedDate')
        self.assertEqual(result['bookmarks']['accounts']['comp-001']['last_record'],
                         '2024-03-15T10:00:00Z')

    def test_updates_bookmark_when_value_is_newer(self):
        state = {'bookmarks': {'accounts': {'comp-001': {
            'field': 'modifiedDate',
            'last_record': '2024-01-01T00:00:00Z',
        }}}}
        result = incorporate(state, 'accounts', 'comp-001', 'modifiedDate',
                             '2024-06-15T10:00:00Z')
        self.assertEqual(result['bookmarks']['accounts']['comp-001']['last_record'],
                         '2024-06-15T10:00:00Z')

    def test_does_not_update_bookmark_when_value_is_older(self):
        state = {'bookmarks': {'accounts': {'comp-001': {
            'field': 'modifiedDate',
            'last_record': '2024-06-15T10:00:00Z',
        }}}}
        result = incorporate(state, 'accounts', 'comp-001', 'modifiedDate',
                             '2024-01-01T00:00:00Z')
        self.assertEqual(result['bookmarks']['accounts']['comp-001']['last_record'],
                         '2024-06-15T10:00:00Z')

    def test_does_not_mutate_original_state(self):
        state = {}
        result = incorporate(state, 'table', 'comp-001', 'field', '2024-01-01T00:00:00Z')
        self.assertNotIn('bookmarks', state)
        self.assertIn('bookmarks', result)


# ---------------------------------------------------------------------------
# state.save_state
# ---------------------------------------------------------------------------

class TestSaveState(unittest.TestCase):

    @patch('tap_codat.state.singer.write_state')
    def test_writes_state_when_not_empty(self, mock_write_state):
        state = {'bookmarks': {'test': {'last_record': '2024-01-01T00:00:00Z'}}}
        save_state(state)
        mock_write_state.assert_called_once_with(state)

    @patch('tap_codat.state.singer.write_state')
    def test_does_not_write_empty_state(self, mock_write_state):
        save_state({})
        mock_write_state.assert_not_called()

    @patch('tap_codat.state.singer.write_state')
    def test_does_not_write_none_state(self, mock_write_state):
        save_state(None)
        mock_write_state.assert_not_called()


# ---------------------------------------------------------------------------
# transform.find_dt_paths
# ---------------------------------------------------------------------------

class TestFindDtPaths(unittest.TestCase):

    def _make_mock_schema(self, fmt=None, properties=None, items=None):
        schema = MagicMock()
        schema.format = fmt
        schema.properties = properties
        schema.items = items
        return schema

    def test_returns_path_for_date_time_field(self):
        schema = self._make_mock_schema(fmt="date-time")
        result = find_dt_paths(schema)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [])

    def test_returns_empty_for_non_datetime_field(self):
        schema = self._make_mock_schema(fmt=None)
        result = find_dt_paths(schema)
        self.assertEqual(result, [])

    def test_finds_nested_datetime_in_properties(self):
        child = self._make_mock_schema(fmt="date-time")
        parent = self._make_mock_schema(properties={"created": child})
        result = find_dt_paths(parent)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [DictKey("created")])

    def test_finds_datetime_in_array_items(self):
        item_schema = self._make_mock_schema(fmt="date-time")
        parent = self._make_mock_schema(items=item_schema)
        result = find_dt_paths(parent)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], [ListItems])

    def test_finds_multiple_dt_paths(self):
        child1 = self._make_mock_schema(fmt="date-time")
        child2 = self._make_mock_schema(fmt="date-time")
        child3 = self._make_mock_schema(fmt=None)
        parent = self._make_mock_schema(
            properties={"created": child1, "updated": child2, "name": child3})
        result = find_dt_paths(parent)
        self.assertEqual(len(result), 2)


# ---------------------------------------------------------------------------
# transform.safe_strftime
# ---------------------------------------------------------------------------

class TestSafeStrftime(unittest.TestCase):

    def test_formats_standard_datetime(self):
        import pendulum
        dt = pendulum.parse("2024-06-15T10:30:00Z")
        result = safe_strftime(dt)
        self.assertIn("2024-06-15", result)
        self.assertIn("10:30:00", result)

    def test_returns_string(self):
        import pendulum
        dt = pendulum.parse("2023-01-01T00:00:00Z")
        result = safe_strftime(dt)
        self.assertIsInstance(result, str)


# ---------------------------------------------------------------------------
# transform.transform_dts
# ---------------------------------------------------------------------------

class TestTransformDts(unittest.TestCase):

    def test_transforms_datetime_field_in_records(self):
        records = [{"date": "2024-06-15T10:00:00.00Z", "name": "test"}]
        paths = [[DictKey("date")]]
        result = transform_dts(records, paths)
        self.assertIn("2024-06-15", result[0]["date"])
        self.assertEqual(result[0]["name"], "test")

    def test_leaves_non_datetime_fields_unchanged(self):
        records = [{"name": "test", "value": 42}]
        paths = []
        result = transform_dts(records, paths)
        self.assertEqual(result[0]["name"], "test")
        self.assertEqual(result[0]["value"], 42)

    def test_empty_records_returns_empty(self):
        result = transform_dts([], [[DictKey("date")]])
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# http.Client construction
# ---------------------------------------------------------------------------

class TestClientConstruction(unittest.TestCase):

    def test_client_sets_base_url_production(self):
        config = {"api_key": "test_key", "uat_urls": "false"}
        client = Client(config)
        self.assertEqual(client.base_url, "https://api.codat.io")

    def test_client_sets_base_url_uat(self):
        config = {"api_key": "test_key", "uat_urls": "true"}
        client = Client(config)
        self.assertEqual(client.base_url, "https://api-uat.codat.io")

    def test_client_encodes_api_key(self):
        from base64 import b64encode
        config = {"api_key": "my_secret_key", "uat_urls": "false"}
        client = Client(config)
        expected = b64encode(b"my_secret_key").decode("utf-8")
        self.assertEqual(client.b64key, expected)

    def test_client_logs_initially_empty(self):
        config = {"api_key": "test_key", "uat_urls": "false"}
        client = Client(config)
        self.assertEqual(client.logs, [])


# ---------------------------------------------------------------------------
# http.Client.request_with_handling
# ---------------------------------------------------------------------------

class TestClientRequestHandling(unittest.TestCase):

    def _make_client(self):
        config = {"api_key": "test_key", "uat_urls": "false"}
        return Client(config)

    def _make_mock_response(self, status_code, json_data=None):
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = json_data or {}
        resp.url = "https://api.codat.io/test"
        resp.raise_for_status = MagicMock()
        return resp

    @patch.object(Client, 'prepare_and_send')
    def test_returns_json_on_200(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_mock_response(200, {"results": []})
        request = MagicMock()
        result = client.request_with_handling(request, "companies")
        self.assertEqual(result, {"results": []})

    @patch.object(Client, 'prepare_and_send')
    def test_returns_empty_results_on_404(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_mock_response(404)
        request = MagicMock()
        result = client.request_with_handling(request, "companies")
        self.assertEqual(result, {"results": []})
        self.assertEqual(len(client.logs), 1)

    @patch.object(Client, 'prepare_and_send')
    def test_returns_none_on_409(self, mock_send):
        client = self._make_client()
        mock_send.return_value = self._make_mock_response(409)
        request = MagicMock()
        result = client.request_with_handling(request, "companies")
        self.assertIsNone(result)
        self.assertEqual(len(client.logs), 1)

    @patch.object(Client, 'prepare_and_send')
    def test_retries_on_429_then_succeeds(self, mock_send):
        """429 status triggers retry; second call succeeds."""
        client = self._make_client()
        mock_send.side_effect = [
            self._make_mock_response(429),
            self._make_mock_response(200, {"results": ["ok"]}),
        ]
        request = MagicMock()
        result = client.request_with_handling(request, "companies")
        self.assertEqual(result, {"results": ["ok"]})
        self.assertEqual(mock_send.call_count, 2)

    @patch.object(Client, 'prepare_and_send')
    def test_retries_on_500_then_succeeds(self, mock_send):
        """500 status triggers retry; second call succeeds."""
        client = self._make_client()
        mock_send.side_effect = [
            self._make_mock_response(500),
            self._make_mock_response(200, {"results": ["ok"]}),
        ]
        request = MagicMock()
        result = client.request_with_handling(request, "companies")
        self.assertEqual(result, {"results": ["ok"]})
        self.assertEqual(mock_send.call_count, 2)


# ---------------------------------------------------------------------------
# http.Client.GET
# ---------------------------------------------------------------------------

class TestClientGET(unittest.TestCase):

    @patch.object(Client, 'request_with_handling')
    def test_get_creates_request_and_calls_handling(self, mock_handling):
        config = {"api_key": "test_key", "uat_urls": "false"}
        client = Client(config)
        mock_handling.return_value = {"results": []}
        result = client.GET({"path": "/companies"}, "companies")
        mock_handling.assert_called_once()
        self.assertEqual(result, {"results": []})


# ---------------------------------------------------------------------------
# context.Context
# ---------------------------------------------------------------------------

class TestContext(CodatBaseTest, unittest.TestCase):

    def test_context_initialization(self):
        ctx = Context(self.default_config, {})
        self.assertEqual(ctx.config, self.default_config)
        self.assertEqual(ctx.state, {})
        self.assertIsInstance(ctx.client, Client)
        self.assertEqual(ctx.cache, {})

    def test_catalog_setter_sets_selected_stream_ids(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies', 'accounts'])
        ctx.catalog = catalog
        self.assertIn('companies', ctx.selected_stream_ids)
        self.assertIn('accounts', ctx.selected_stream_ids)
        self.assertNotIn('invoices', ctx.selected_stream_ids)

    def test_catalog_setter_sets_schema_dt_paths(self):
        ctx = self._create_context()
        catalog = self._make_selected_catalog()
        ctx.catalog = catalog
        self.assertIn('companies', ctx.schema_dt_paths)
        self.assertIn('accounts', ctx.schema_dt_paths)
        self.assertIsInstance(ctx.schema_dt_paths['companies'], list)

    @patch('tap_codat.context.singer.write_state')
    def test_write_state(self, mock_write_state):
        ctx = Context(self.default_config, {'bookmarks': {}})
        ctx.write_state()
        mock_write_state.assert_called_once_with({'bookmarks': {}})


# ---------------------------------------------------------------------------
# streams.format_response
# ---------------------------------------------------------------------------

class TestFormatResponse(unittest.TestCase):

    def test_collection_with_key(self):
        from tap_codat.streams import Paginated
        stream = Paginated("accounts", ["id", "companyId"],
                           "/companies/{companyId}/data/accounts",
                           collection_key="results")
        company = {"id": "comp-001"}
        response = {"results": [{"id": "acct-001", "name": "Cash"}]}
        records = stream.format_response(response, company)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyId"], "comp-001")
        self.assertEqual(records[0]["id"], "acct-001")

    def test_collection_without_key(self):
        from tap_codat.streams import Basic
        stream = Basic("bank_statements", ["accountName", "companyId"],
                       "/companies/{companyId}/data/bankStatements")
        company = {"id": "comp-001"}
        response = [{"accountName": "Checking"}]
        records = stream.format_response(response, company)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyId"], "comp-001")

    def test_non_collection_single_object(self):
        from tap_codat.streams import Basic
        stream = Basic("company_info", ["companyId"],
                       "/companies/{companyId}/data/info",
                       returns_collection=False)
        company = {"id": "comp-001"}
        response = {"companyName": "Test Corp"}
        records = stream.format_response(response, company)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["companyName"], "Test Corp")
        self.assertEqual(records[0]["companyId"], "comp-001")

    def test_non_collection_none_response(self):
        from tap_codat.streams import Basic
        stream = Basic("company_info", ["companyId"],
                       "/companies/{companyId}/data/info",
                       returns_collection=False)
        company = {"id": "comp-001"}
        records = stream.format_response(None, company)
        self.assertEqual(len(records), 0)

    def test_extras_added_to_records(self):
        from tap_codat.streams import Paginated
        stream = Paginated("bank_accounts", ["accountName", "companyId"],
                           "/test", collection_key="results")
        company = {"id": "comp-001"}
        response = {"results": [{"accountName": "Checking"}]}
        records = stream.format_response(response, company, {"connectionId": "conn-001"})
        self.assertEqual(records[0]["connectionId"], "conn-001")


# ---------------------------------------------------------------------------
# streams.flatten_report
# ---------------------------------------------------------------------------

class TestFlattenReport(unittest.TestCase):

    def test_flat_item(self):
        item = {"name": "Assets", "value": 50000, "items": []}
        result = flatten_report(item)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "Assets")
        self.assertEqual(result[0]["value"], 50000)
        self.assertEqual(result[0]["name_0"], "Assets")

    def test_nested_items(self):
        item = {
            "name": "Assets",
            "value": 100,
            "items": [
                {"name": "Cash", "value": 60, "items": []},
                {"name": "Receivables", "value": 40, "items": []},
            ],
        }
        result = flatten_report(item)
        self.assertEqual(len(result), 3)
        names = [r["name"] for r in result]
        self.assertIn("Assets", names)
        self.assertIn("Cash", names)
        self.assertIn("Receivables", names)

    def test_accountId_included(self):
        item = {"name": "Cash", "value": 100, "accountId": "acct-001"}
        result = flatten_report(item)
        self.assertEqual(result[0]["accountId"], "acct-001")

    def test_accountId_none_when_missing(self):
        item = {"name": "Cash", "value": 100}
        result = flatten_report(item)
        self.assertIsNone(result[0]["accountId"])


# ---------------------------------------------------------------------------
# streams.flatten_balance_sheets
# ---------------------------------------------------------------------------

class TestFlattenBalanceSheets(unittest.TestCase):

    def test_flattens_reports(self):
        balance_sheets = [{
            "reports": [{
                "assets": {"name": "Assets", "value": 100, "items": []},
                "liabilities": {"name": "Liabilities", "value": 50, "items": []},
                "equity": {"name": "Equity", "value": 50, "items": []},
            }],
        }]
        result = flatten_balance_sheets(balance_sheets)
        report = result[0]["reports"][0]
        self.assertIsInstance(report["assets"], list)
        self.assertIsInstance(report["liabilities"], list)
        self.assertIsInstance(report["equity"], list)
        self.assertEqual(report["assets"][0]["name"], "Assets")


# ---------------------------------------------------------------------------
# streams.flatten_profit_and_loss
# ---------------------------------------------------------------------------

class TestFlattenProfitAndLoss(unittest.TestCase):

    def test_flattens_reports(self):
        pnls = [{
            "reports": [{
                "income": {"name": "Income", "value": 1000, "items": []},
                "costOfSales": {"name": "Cost of Sales", "value": 300, "items": []},
                "expenses": {"name": "Expenses", "value": 200, "items": []},
                "otherIncome": {"name": "Other Income", "value": 50, "items": []},
                "otherExpenses": {"name": "Other Expenses", "value": 10, "items": []},
            }],
        }]
        result = flatten_profit_and_loss(pnls)
        report = result[0]["reports"][0]
        for key in ["income", "costOfSales", "expenses", "otherIncome", "otherExpenses"]:
            self.assertIsInstance(report[key], list)
            self.assertEqual(len(report[key]), 1)


# ---------------------------------------------------------------------------
# streams.trunc_payment_allocation_notes
# ---------------------------------------------------------------------------

class TestTruncPaymentAllocationNotes(unittest.TestCase):

    def test_truncates_long_note(self):
        invoices = [{
            "paymentAllocations": [{"note": "x" * 2000}],
        }]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(len(result[0]["paymentAllocations"][0]["note"]), 1024)

    def test_preserves_short_note(self):
        invoices = [{
            "paymentAllocations": [{"note": "short note"}],
        }]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["paymentAllocations"][0]["note"], "short note")

    def test_no_payment_allocations(self):
        invoices = [{"id": "inv-001"}]
        result = trunc_payment_allocation_notes(invoices)
        self.assertEqual(result[0]["id"], "inv-001")


# ---------------------------------------------------------------------------
# streams.capture_state
# ---------------------------------------------------------------------------

class TestCaptureState(CodatBaseTest, unittest.TestCase):

    def test_get_max_returns_start_date_when_no_state(self):
        ctx = self._create_context()
        ctx.state = {}
        with capture_state(ctx, "accounts", "modifiedDate", "comp-001") as sync:
            result = sync.get_max()
        self.assertEqual(result, self.default_config["start_date"])

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


# ---------------------------------------------------------------------------
# __init__.load_schema
# ---------------------------------------------------------------------------

class TestLoadSchema(unittest.TestCase):

    def test_loads_companies_schema(self):
        ctx = MagicMock()
        schema = tap_codat.load_schema(ctx, "companies")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])

    def test_loads_accounts_schema(self):
        ctx = MagicMock()
        schema = tap_codat.load_schema(ctx, "accounts")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])
        self.assertIn("companyId", schema["properties"])

    def test_loads_balance_sheets_schema_with_dependencies(self):
        ctx = MagicMock()
        schema = tap_codat.load_schema(ctx, "balance_sheets")
        self.assertIn("properties", schema)
        self.assertIn("reports", schema["properties"])


# ---------------------------------------------------------------------------
# __init__.discover
# ---------------------------------------------------------------------------

class TestDiscover(CodatBaseTest, unittest.TestCase):

    def test_discover_returns_catalog(self):
        catalog = self._run_discover()
        self.assertIsNotNone(catalog)
        self.assertTrue(len(catalog.streams) > 0)

    def test_discover_returns_all_streams(self):
        catalog = self._run_discover()
        stream_ids = {entry.tap_stream_id for entry in catalog.streams}
        self.assertEqual(stream_ids, self.ALL_STREAM_IDS)

    def test_discover_sets_key_properties(self):
        catalog = self._run_discover()
        expected = self.expected_metadata()
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                self.assertEqual(
                    set(entry.key_properties),
                    expected[entry.tap_stream_id][self.PRIMARY_KEYS],
                )


# ---------------------------------------------------------------------------
# Sync with mocked API (unit-level tests of stream sync)
# ---------------------------------------------------------------------------

class TestSyncCompanies(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_companies_sync_writes_records(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies'])
        ctx.catalog = catalog
        # Simulate fetch_into_cache
        from tap_codat.streams import companies
        companies.fetch_into_cache(ctx)
        companies.sync(ctx)
        mock_write_records.assert_called()
        records = mock_write_records.call_args[0][1]
        self.assertEqual(len(records), len(self.MOCK_COMPANIES))

    @patch("tap_codat.streams.singer.write_records")
    def test_companies_records_have_id(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies'])
        ctx.catalog = catalog
        from tap_codat.streams import companies
        companies.fetch_into_cache(ctx)
        companies.sync(ctx)
        records = mock_write_records.call_args[0][1]
        for record in records:
            self.assertIn("id", record)


class TestSyncAccounts(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_accounts_sync_writes_records(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies', 'accounts'])
        ctx.catalog = catalog
        from tap_codat import streams as st
        st.companies.fetch_into_cache(ctx)
        # Find the accounts stream and sync
        accounts_stream = next(s for s in st.all_streams
                               if s.tap_stream_id == 'accounts')
        accounts_stream.sync(ctx)
        mock_write_records.assert_called()
        stream_name = mock_write_records.call_args[0][0]
        self.assertEqual(stream_name, "accounts")

    @patch("tap_codat.streams.singer.write_records")
    def test_accounts_records_have_company_id(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies', 'accounts'])
        ctx.catalog = catalog
        from tap_codat import streams as st
        st.companies.fetch_into_cache(ctx)
        accounts_stream = next(s for s in st.all_streams
                               if s.tap_stream_id == 'accounts')
        accounts_stream.sync(ctx)
        records = mock_write_records.call_args[0][1]
        for record in records:
            self.assertIn("companyId", record)
            self.assertEqual(record["companyId"], "comp-001")


class TestSyncInvoices(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_invoices_sync_writes_records(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(stream_names=['companies', 'invoices'])
        ctx.catalog = catalog
        from tap_codat import streams as st
        st.companies.fetch_into_cache(ctx)
        invoices_stream = next(s for s in st.all_streams
                               if s.tap_stream_id == 'invoices')
        invoices_stream.sync(ctx)
        mock_write_records.assert_called()
        stream_name = mock_write_records.call_args[0][0]
        self.assertEqual(stream_name, "invoices")


class TestSyncCompanyInfo(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    def test_company_info_sync_writes_single_record(self, mock_write_records):
        ctx = self._create_context()
        catalog = self._make_selected_catalog(
            stream_names=['companies', 'company_info'])
        ctx.catalog = catalog
        from tap_codat import streams as st
        st.companies.fetch_into_cache(ctx)
        info_stream = next(s for s in st.all_streams
                           if s.tap_stream_id == 'company_info')
        info_stream.sync(ctx)
        mock_write_records.assert_called()
        records = mock_write_records.call_args[0][1]
        self.assertEqual(len(records), 1)
        self.assertIn("companyId", records[0])


if __name__ == '__main__':
    unittest.main()
