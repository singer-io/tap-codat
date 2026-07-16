"""Unit tests for tap_codat discovery — load_schema, add_stream_to_catalog,
discover, and stream configuration."""

import os
import unittest
from unittest.mock import MagicMock

from singer import metadata
from singer.catalog import Catalog

import tap_codat
from tap_codat import streams as streams_
from tap_codat.context import Context
from tap_codat.http import CodatForbiddenError


default_config = {
    "api_key": "test_api_key_12345",
    "start_date": "2023-01-01T00:00:00Z",
    "uat_urls": "false",
}


def _create_mock_context(config=None, state=None):
    cfg = config or dict(default_config)
    ctx = Context(cfg, state or {})
    ctx.client.GET = MagicMock(return_value={"results": [{"id": "comp-001", "name": "Mock"}]})
    return ctx


# ---------------------------------------------------------------------------
# get_abs_path
# ---------------------------------------------------------------------------

class TestGetAbsPath(unittest.TestCase):

    def test_returns_absolute_path(self):
        result = tap_codat.get_abs_path("schemas/companies.json")
        self.assertTrue(os.path.isabs(result))

    def test_path_contains_schemas(self):
        result = tap_codat.get_abs_path("schemas/accounts.json")
        self.assertIn("schemas", result)
        self.assertIn("accounts.json", result)


# ---------------------------------------------------------------------------
# load_schema
# ---------------------------------------------------------------------------

class TestLoadSchema(unittest.TestCase):

    def test_loads_companies_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "companies")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])

    def test_loads_accounts_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "accounts")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])
        self.assertIn("companyId", schema["properties"])

    def test_loads_invoices_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "invoices")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])

    def test_loads_bills_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "bills")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])

    def test_loads_company_info_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "company_info")
        self.assertIn("properties", schema)
        self.assertIn("companyId", schema["properties"])

    def test_loads_events_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "events")
        self.assertIn("properties", schema)
        self.assertIn("eventTimeUtc", schema["properties"])

    def test_loads_connections_schema(self):
        schema = tap_codat.load_schema(MagicMock(), "connections")
        self.assertIn("properties", schema)
        self.assertIn("id", schema["properties"])

    def test_loads_balance_sheets_schema_with_dependencies(self):
        schema = tap_codat.load_schema(MagicMock(), "balance_sheets")
        self.assertIn("properties", schema)
        self.assertIn("reports", schema["properties"])
        # Should not have tap_schema_dependencies after loading
        self.assertNotIn("tap_schema_dependencies", schema)

    def test_loads_profit_and_loss_schema_with_dependencies(self):
        schema = tap_codat.load_schema(MagicMock(), "profit_and_loss")
        self.assertIn("properties", schema)
        self.assertNotIn("tap_schema_dependencies", schema)

    def test_schema_has_type(self):
        schema = tap_codat.load_schema(MagicMock(), "companies")
        self.assertIn("type", schema)

    def test_all_stream_schemas_loadable(self):
        """Every stream defined in all_streams has a loadable schema."""
        for stream in streams_.all_streams:
            with self.subTest(stream=stream.tap_stream_id):
                schema = tap_codat.load_schema(MagicMock(), stream.tap_stream_id)
                self.assertIn("properties", schema)

    def test_all_substream_schemas_loadable(self):
        """Every substream defined in all_streams has a loadable schema."""
        for stream in streams_.all_streams:
            for sub in stream.substreams:
                with self.subTest(stream=sub.tap_stream_id):
                    schema = tap_codat.load_schema(MagicMock(), sub.tap_stream_id)
                    self.assertIn("properties", schema)


# ---------------------------------------------------------------------------
# add_stream_to_catalog
# ---------------------------------------------------------------------------

class TestAddStreamToCatalog(unittest.TestCase):

    def test_adds_entry_to_catalog(self):
        catalog = Catalog([])
        ctx = _create_mock_context()
        tap_codat.add_stream_to_catalog(catalog, ctx, streams_.companies)
        self.assertEqual(len(catalog.streams), 1)
        self.assertEqual(catalog.streams[0].tap_stream_id, "companies")

    def test_entry_has_key_properties(self):
        catalog = Catalog([])
        ctx = _create_mock_context()
        tap_codat.add_stream_to_catalog(catalog, ctx, streams_.companies)
        self.assertEqual(catalog.streams[0].key_properties, ["id"])

    def test_entry_has_schema(self):
        catalog = Catalog([])
        ctx = _create_mock_context()
        tap_codat.add_stream_to_catalog(catalog, ctx, streams_.companies)
        schema = catalog.streams[0].schema.to_dict()
        self.assertIn("properties", schema)

    def test_entry_has_metadata(self):
        catalog = Catalog([])
        ctx = _create_mock_context()
        tap_codat.add_stream_to_catalog(catalog, ctx, streams_.companies)
        self.assertIsNotNone(catalog.streams[0].metadata)
        self.assertTrue(len(catalog.streams[0].metadata) > 0)

    def test_all_fields_marked_automatic(self):
        """All field-level metadata entries have inclusion=automatic."""
        catalog = Catalog([])
        ctx = _create_mock_context()
        tap_codat.add_stream_to_catalog(catalog, ctx, streams_.companies)
        mdata = metadata.to_map(catalog.streams[0].metadata)
        schema_props = catalog.streams[0].schema.to_dict()["properties"]
        for field_name in schema_props:
            inclusion = mdata.get(("properties", field_name), {}).get("inclusion")
            self.assertEqual(inclusion, "automatic", f"{field_name} not automatic")


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------

class TestDiscover(unittest.TestCase):

    def test_returns_catalog(self):
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        self.assertIsInstance(catalog, Catalog)

    def test_all_streams_present(self):
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        stream_ids = {e.tap_stream_id for e in catalog.streams}
        expected = {
            "companies", "accounts", "bank_accounts", "bank_account_transactions",
            "bank_statements", "bank_statement_lines", "bills", "company_info",
            "credit_notes", "customers", "payments", "suppliers", "connections",
            "bill_payments", "invoices", "journal_entries", "items", "tax_rates",
            "events", "balance_sheets", "profit_and_loss",
        }
        self.assertEqual(stream_ids, expected)

    def test_each_entry_has_schema(self):
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema = entry.schema.to_dict()
                self.assertIn("properties", schema)
                self.assertTrue(len(schema["properties"]) > 0)

    def test_each_entry_has_key_properties(self):
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                self.assertIsNotNone(entry.key_properties)
                self.assertTrue(len(entry.key_properties) > 0)

    def test_each_entry_has_metadata(self):
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                self.assertIsNotNone(entry.metadata)
                self.assertTrue(len(entry.metadata) > 0)

    def test_key_properties_in_schema(self):
        """Key properties listed must exist in schema properties."""
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema_props = set(entry.schema.to_dict().get("properties", {}).keys())
                key_props = set(entry.key_properties or [])
                self.assertTrue(
                    key_props.issubset(schema_props),
                    f"{entry.tap_stream_id}: keys {key_props} not in {schema_props}",
                )

    def test_checks_credentials(self):
        """discover calls check_credentials_are_authorized (companies.raw_fetch)."""
        ctx = _create_mock_context()
        tap_codat.discover(ctx)
        ctx.client.GET.assert_called()


# ---------------------------------------------------------------------------
# Stream definitions — all_streams config
# ---------------------------------------------------------------------------

class TestAllStreamsConfig(unittest.TestCase):

    def test_all_streams_have_pk_fields(self):
        for stream in streams_.all_streams:
            with self.subTest(stream=stream.tap_stream_id):
                self.assertIsInstance(stream.pk_fields, list)
                self.assertTrue(len(stream.pk_fields) > 0)

    def test_all_streams_have_path(self):
        for stream in streams_.all_streams:
            with self.subTest(stream=stream.tap_stream_id):
                self.assertIsNotNone(stream.path)

    def test_all_stream_ids_matches(self):
        """all_stream_ids list matches tap_stream_id from all_streams."""
        ids_from_list = streams_.all_stream_ids
        ids_from_streams = [s.tap_stream_id for s in streams_.all_streams]
        self.assertEqual(ids_from_list, ids_from_streams)

    def test_expected_stream_names(self):
        expected = {
            "companies", "accounts", "bank_accounts", "bank_statements",
            "bills", "company_info", "credit_notes", "customers", "payments",
            "suppliers", "connections", "bill_payments", "invoices",
            "journal_entries", "items", "tax_rates", "events",
            "balance_sheets", "profit_and_loss",
        }
        actual = {s.tap_stream_id for s in streams_.all_streams}
        self.assertEqual(actual, expected)

    def test_paginated_streams_have_state_filter(self):
        """Paginated streams with collection_key should have state_filter."""
        from tap_codat.streams import Paginated
        for stream in streams_.all_streams:
            if isinstance(stream, Paginated) and stream.tap_stream_id != "bank_accounts":
                with self.subTest(stream=stream.tap_stream_id):
                    self.assertIsNotNone(
                        stream.state_filter,
                        f"{stream.tap_stream_id} is Paginated but has no state_filter",
                    )

    def test_paginated_streams_have_collection_key(self):
        from tap_codat.streams import Paginated
        for stream in streams_.all_streams:
            if isinstance(stream, Paginated):
                with self.subTest(stream=stream.tap_stream_id):
                    self.assertIsNotNone(stream.collection_key)

    def test_substreams_list(self):
        """Verify only bank_accounts and bank_statements have substreams."""
        streams_with_subs = {
            s.tap_stream_id for s in streams_.all_streams if s.substreams
        }
        self.assertEqual(streams_with_subs, {"bank_accounts", "bank_statements"})


# ---------------------------------------------------------------------------
# Access check — stream exclusion during discovery
# ---------------------------------------------------------------------------

class TestAccessChecks(unittest.TestCase):

    def test_all_streams_accessible(self):
        """When no 403 is raised, all streams remain in the catalog."""
        ctx = _create_mock_context()
        catalog = tap_codat.discover(ctx)
        stream_ids = {e.tap_stream_id for e in catalog.streams}
        self.assertIn("companies", stream_ids)
        self.assertIn("invoices", stream_ids)

    def test_partial_access_excludes_forbidden_stream(self):
        """A stream returning 403 is excluded from the catalog."""
        from tap_codat.http import CodatForbiddenError

        ctx = _create_mock_context()
        forbidden_stream = "invoices"

        original_get = ctx.client.GET

        def side_effect(request_kwargs, tap_stream_id):
            if tap_stream_id == forbidden_stream:
                raise CodatForbiddenError("403 Forbidden")
            return original_get(request_kwargs, tap_stream_id)

        ctx.client.GET = MagicMock(side_effect=side_effect)

        catalog = tap_codat.discover(ctx)
        stream_ids = {e.tap_stream_id for e in catalog.streams}
        self.assertNotIn(forbidden_stream, stream_ids)
        self.assertIn("companies", stream_ids)

    def test_all_streams_forbidden_raises_error(self):
        """When all streams are forbidden, CodatForbiddenError is raised."""
        from tap_codat.http import CodatForbiddenError

        ctx = _create_mock_context()

        def always_forbidden(request_kwargs, tap_stream_id):
            raise CodatForbiddenError("403 Forbidden")

        ctx.client.GET = MagicMock(side_effect=always_forbidden)

        with self.assertRaises(CodatForbiddenError):
            tap_codat.discover(ctx)

    def test_substreams_excluded_when_parent_forbidden(self):
        """Substreams are excluded when their parent stream is forbidden."""
        ctx = _create_mock_context()
        forbidden_stream = "bank_accounts"

        original_get = ctx.client.GET

        def side_effect(request_kwargs, tap_stream_id):
            if tap_stream_id == forbidden_stream:
                raise CodatForbiddenError("403 Forbidden")
            return original_get(request_kwargs, tap_stream_id)

        ctx.client.GET = MagicMock(side_effect=side_effect)

        catalog = tap_codat.discover(ctx)
        stream_ids = {e.tap_stream_id for e in catalog.streams}
        self.assertNotIn("bank_accounts", stream_ids)
        self.assertNotIn("bank_account_transactions", stream_ids)


class TestAccessCheckHelpers(unittest.TestCase):

    def test_check_credentials_are_authorized_calls_companies_raw_fetch(self):
        ctx = _create_mock_context()
        original = streams_.companies.raw_fetch
        streams_.companies.raw_fetch = MagicMock(return_value={"results": [{"id": "comp-001"}]})
        try:
            tap_codat.check_credentials_are_authorized(ctx)
            streams_.companies.raw_fetch.assert_called_once_with(ctx)
        finally:
            streams_.companies.raw_fetch = original

    def test_apply_access_checks_raises_when_no_stream_accessible(self):
        ctx = _create_mock_context()

        inaccessible = [
            MagicMock(tap_stream_id="accounts", check_access=MagicMock(return_value=False)),
            MagicMock(tap_stream_id="invoices", check_access=MagicMock(return_value=False)),
        ]

        with self.assertRaises(CodatForbiddenError):
            tap_codat._apply_access_checks(ctx, inaccessible)

    def test_companies_stream_check_access_uses_root_path(self):
        stream = streams_.Stream("companies", ["id"], "/companies")
        ctx = MagicMock()
        ctx.client.GET = MagicMock(return_value={"results": []})

        self.assertTrue(stream.check_access(ctx))
        ctx.client.GET.assert_called_once_with({"path": "/companies"}, "companies")

    def test_company_scoped_stream_without_company_context_returns_true(self):
        stream = streams_.Stream("accounts", ["id"], "/companies/{companyId}/data/accounts")
        ctx = MagicMock()
        ctx.client.GET = MagicMock()

        self.assertTrue(stream.check_access(ctx, company_id=None))
        ctx.client.GET.assert_not_called()

    @unittest.mock.patch("tap_codat.streams.LOGGER.warning")
    def test_connection_fetch_forbidden_excludes_connection_scoped_stream(self, mock_warn):
        stream = streams_.Stream(
            "bank_accounts",
            ["accountName", "companyId", "connectionId"],
            "/companies/{companyId}/connections/{connectionId}/data/bankAccounts",
        )
        ctx = MagicMock()
        ctx.client.GET = MagicMock(side_effect=CodatForbiddenError("forbidden connections"))

        self.assertFalse(stream.check_access(ctx, company_id="comp-001"))
        self.assertTrue(mock_warn.called)

    def test_connection_scoped_stream_without_connections_stays_accessible(self):
        stream = streams_.Stream(
            "bank_accounts",
            ["accountName", "companyId", "connectionId"],
            "/companies/{companyId}/connections/{connectionId}/data/bankAccounts",
        )
        ctx = MagicMock()
        # First GET fetches connections and returns empty list => no probe path
        ctx.client.GET = MagicMock(return_value=[])

        self.assertTrue(stream.check_access(ctx, company_id="comp-001"))
        self.assertEqual(ctx.client.GET.call_count, 1)
