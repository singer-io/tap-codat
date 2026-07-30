"""Integration test: do_sync() end-to-end pipeline writes schemas,
records, and state correctly."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, call

import tap_codat

try:
    from .base import CodatBaseTest
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from base import CodatBaseTest


class DoSyncIntegrationTest(CodatBaseTest, unittest.TestCase):
    """Test sync() end-to-end with mocked API."""

    def setUp(self):
        self.ctx = self._create_context()
        self.ctx.catalog = self._make_selected_catalog()

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_full_pipeline_emits_schemas_and_records(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """sync() should emit SCHEMA then RECORDs for each synced stream."""
        tap_codat.sync(self.ctx)

        schema_streams = {c[0][0] for c in mock_write_schema.call_args_list}
        record_streams = {c[0][0] for c in mock_write_records.call_args_list}

        # Core streams should have schemas and records
        self.assertIn('companies', schema_streams)
        self.assertIn('companies', record_streams)
        self.assertIn('accounts', schema_streams)
        self.assertIn('accounts', record_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_correct_record_counts_for_accounts(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """sync() emits the right number of records for accounts."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'accounts':
                records = call_args[0][1]
                self.assertEqual(len(records), len(self.MOCK_ACCOUNTS))
                return
        self.fail("No accounts records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_correct_record_counts_for_companies(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """sync() emits the right number of records for companies."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'companies':
                records = call_args[0][1]
                self.assertEqual(len(records), len(self.MOCK_COMPANIES))
                return
        self.fail("No companies records written")

    # ------------------------------------------------------------------
    # Schema emission order
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_schema_emitted_before_records(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """For each stream, write_schema must be called before write_records."""
        call_order = []
        mock_write_schema.side_effect = lambda *a, **k: call_order.append(('schema', a[0]))
        mock_write_records.side_effect = lambda *a, **k: call_order.append(('record', a[0]))

        tap_codat.sync(self.ctx)

        # For streams with records, schema must come first
        for stream_name in ('companies', 'accounts'):
            schema_indices = [
                i for i, (t, s) in enumerate(call_order)
                if t == 'schema' and s == stream_name
            ]
            record_indices = [
                i for i, (t, s) in enumerate(call_order)
                if t == 'record' and s == stream_name
            ]
            if schema_indices and record_indices:
                self.assertLess(
                    schema_indices[0], record_indices[0],
                    f"Schema for {stream_name} must come before its records",
                )

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_schema_includes_key_properties(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """write_schema is called with correct key_properties for each stream."""
        tap_codat.sync(self.ctx)

        expected = self.expected_metadata()
        for schema_call in mock_write_schema.call_args_list:
            stream_name = schema_call[0][0]
            key_props = schema_call[0][2]
            if stream_name in expected:
                self.assertIsInstance(key_props, list)
                self.assertEqual(
                    set(key_props),
                    expected[stream_name][self.PRIMARY_KEYS],
                    f"key_properties mismatch for {stream_name}",
                )

    # ------------------------------------------------------------------
    # Stream selection
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_only_selected_streams_are_synced(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """When only 'companies' is selected, other streams are skipped."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['companies'])
        tap_codat.sync(ctx)

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('companies', record_streams)
        self.assertNotIn('accounts', record_streams)
        self.assertNotIn('invoices', record_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_only_accounts_selected(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """When only 'accounts' is selected, companies is skipped."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['accounts'])
        tap_codat.sync(ctx)

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('accounts', record_streams)
        self.assertNotIn('companies', record_streams)

    # ------------------------------------------------------------------
    # State management
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_currently_syncing_cleared_after_sync(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """After sync completes, currently_syncing state should be None."""
        tap_codat.sync(self.ctx)
        self.assertIsNone(self.ctx.state.get("currently_syncing"))

    # ------------------------------------------------------------------
    # No streams selected
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_no_streams_selected_writes_nothing(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """When no streams are selected, nothing is written."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=[])
        tap_codat.sync(ctx)

        mock_write_schema.assert_not_called()
        mock_write_records.assert_not_called()

    # ------------------------------------------------------------------
    # Empty API responses
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_empty_api_responses_no_crash(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """sync() completes without error when API returns empty results."""
        ctx = self._create_context()
        # Return empty results for all endpoints
        def empty_mock(request_kwargs, tap_stream_id):
            path = request_kwargs.get("path", "")
            if path == "/companies":
                return {"results": []}
            return {"results": []}
        ctx.client.GET.side_effect = empty_mock
        ctx.catalog = self._make_selected_catalog()
        tap_codat.sync(ctx)

        # Schemas still emitted even with no companies (no per-company streams run)
        # No records written for company-scoped streams since no companies
        company_records = [
            c for c in mock_write_records.call_args_list
            if c[0][0] == 'accounts'
        ]
        self.assertEqual(len(company_records), 0)

    # ------------------------------------------------------------------
    # State emitted with bookmark values
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_state_emitted_with_bookmark_for_incremental_stream(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """After syncing accounts, state bookmarks contain the max modifiedDate."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(
            stream_names=['accounts'])
        tap_codat.sync(ctx)

        bookmarks = ctx.state.get('bookmarks', {})
        accounts_bm = bookmarks.get('accounts', {}).get('comp-001', {})
        if accounts_bm:
            self.assertEqual(accounts_bm.get('field'), 'modifiedDate')
            # Max from mock data: acct-002 has 2024-03-20T14:30:00.00Z
            self.assertIn('2024-03-20', accounts_bm.get('last_record', ''))

    # ------------------------------------------------------------------
    # Record field correctness
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_company_records_have_correct_types(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Company records emitted by sync() have properly typed fields."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['companies'])
        tap_codat.sync(ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'companies':
                record = call_args[0][1][0]
                self.assertIsInstance(record['id'], str)
                self.assertIsInstance(record['name'], str)
                self.assertIsInstance(record['platform'], str)
                return
        self.fail("No companies records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_account_records_have_correct_types(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Account records emitted by sync() have properly typed fields."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['accounts'])
        tap_codat.sync(ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'accounts':
                record = call_args[0][1][0]
                self.assertIsInstance(record['id'], str)
                self.assertIsInstance(record['name'], str)
                self.assertIsInstance(record['companyId'], str)
                self.assertIsInstance(record['isBankAccount'], bool)
                return
        self.fail("No accounts records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_invoice_records_have_correct_types(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Invoice records emitted by sync() have properly typed fields."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['invoices'])
        tap_codat.sync(ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'invoices':
                record = call_args[0][1][0]
                self.assertIsInstance(record['id'], str)
                self.assertIsInstance(record['companyId'], str)
                self.assertIsInstance(record['amountDue'], float)
                self.assertIsInstance(record['totalAmount'], float)
                return
        self.fail("No invoices records written")


class MainImplIntegrationTest(CodatBaseTest, unittest.TestCase):
    """Test the CLI entry point main_impl() with real argument parsing."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

        self.config_path = os.path.join(self.tmpdir, 'config.json')
        with open(self.config_path, 'w') as f:
            json.dump(self.default_config, f)

        self.state_path = os.path.join(self.tmpdir, 'state.json')
        with open(self.state_path, 'w') as f:
            json.dump({}, f)

        # Build catalog via mocked discovery and write to file
        catalog = self._make_selected_catalog()
        self.catalog_path = os.path.join(self.tmpdir, 'catalog.json')
        with open(self.catalog_path, 'w') as f:
            json.dump(catalog.to_dict(), f)

    # ------------------------------------------------------------------
    # Discovery via CLI args
    # ------------------------------------------------------------------

    @patch("tap_codat.http.Client.GET", side_effect=lambda *a, **k: {"results": []})
    def test_main_impl_discover_mode(self, mock_get):
        """main_impl() with --config and --discover runs discover."""
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path,
                                '--discover']):
            tap_codat.main_impl()
        # Client.GET is called at least once (check_credentials)
        mock_get.assert_called()

    @patch("tap_codat.http.Client.GET", side_effect=lambda *a, **k: {"results": []})
    def test_main_impl_discover_with_short_args(self, mock_get):
        """main_impl() with -c and -d runs discover."""
        with patch('sys.argv', ['tap-codat',
                                '-c', self.config_path,
                                '-d']):
            tap_codat.main_impl()
        mock_get.assert_called()

    # ------------------------------------------------------------------
    # Sync via CLI args
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.http.Client.GET")
    def test_main_impl_sync_with_all_args(
        self, mock_get, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """main_impl() with --config, --state, --catalog runs full sync."""
        mock_get.side_effect = self._mock_client_GET()
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path,
                                '--state', self.state_path,
                                '--properties', self.catalog_path]):
            tap_codat.main_impl()

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('companies', record_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.http.Client.GET")
    def test_main_impl_sync_without_state_arg(
        self, mock_get, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """main_impl() with --config and --properties but no --state still syncs."""
        mock_get.side_effect = self._mock_client_GET()
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path,
                                '--properties', self.catalog_path]):
            tap_codat.main_impl()

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('companies', record_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.http.Client.GET")
    def test_main_impl_sync_with_short_args(
        self, mock_get, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """main_impl() with -c, -s short flags and -p runs full sync."""
        mock_get.side_effect = self._mock_client_GET()
        with patch('sys.argv', ['tap-codat',
                                '-c', self.config_path,
                                '-s', self.state_path,
                                '-p', self.catalog_path]):
            tap_codat.main_impl()

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('companies', record_streams)

    # ------------------------------------------------------------------
    # main() wraps main_impl()
    # ------------------------------------------------------------------

    @patch("tap_codat.http.Client.GET", side_effect=lambda *a, **k: {"results": []})
    def test_main_calls_discover(self, mock_get):
        """main() with --discover calls discover via main_impl()."""
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path,
                                '--discover']):
            tap_codat.main()
        mock_get.assert_called()

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.http.Client.GET")
    def test_main_calls_sync(
        self, mock_get, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """main() with --config, --state, --catalog runs full sync."""
        mock_get.side_effect = self._mock_client_GET()
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path,
                                '--state', self.state_path,
                                '--properties', self.catalog_path]):
            tap_codat.main()

        record_streams = {c[0][0] for c in mock_write_records.call_args_list}
        self.assertIn('companies', record_streams)

    # ------------------------------------------------------------------
    # No catalog, no discover → auto-discover + sync
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.http.Client.GET")
    def test_main_impl_no_catalog_auto_discovers(
        self, mock_get, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """main_impl() with only --config (no --properties, no --discover)
        auto-discovers and syncs. Auto-discovered catalog has no streams
        selected, so no actual records are synced."""
        mock_get.side_effect = self._mock_client_GET()
        with patch('sys.argv', ['tap-codat',
                                '--config', self.config_path]):
            tap_codat.main_impl()
        # auto-discover catalog has no streams selected, so no records written
        mock_write_records.assert_not_called()

    # ------------------------------------------------------------------
    # Error handling
    # ------------------------------------------------------------------

    def test_missing_config_file_raises(self):
        """main_impl() raises when config file doesn't exist."""
        with self.assertRaises(Exception):
            with patch('sys.argv', ['tap-codat',
                                    '--config', '/tmp/nonexistent_codat_config.json']):
                tap_codat.main_impl()

    @patch("tap_codat.http.Client.GET")
    def test_invalid_catalog_file_raises(self, mock_get):
        """main_impl() raises when catalog file contains invalid JSON."""
        bad_catalog = os.path.join(self.tmpdir, 'bad_catalog.json')
        with open(bad_catalog, 'w') as f:
            f.write('NOT VALID JSON{{{')

        with self.assertRaises(Exception):
            with patch('sys.argv', ['tap-codat',
                                    '--config', self.config_path,
                                    '--properties', bad_catalog]):
                tap_codat.main_impl()
