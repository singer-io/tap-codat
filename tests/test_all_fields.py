"""Integration test: sync all streams with mocked API responses
and verify all fields are replicated."""
import unittest
from unittest.mock import patch

import tap_codat

try:
    from .base import CodatBaseTest
except ImportError:
    from base import CodatBaseTest


# Pre-defined expected field sets for streams with mock data.
# These match the mock data defined in base.py + injected fields (companyId etc.)
COMPANY_FIELDS = {
    "id", "name", "platform", "lastSync", "redirect",
    "status", "dataConnections",
}

ACCOUNT_FIELDS = {
    "id", "name", "description", "nominalCode", "isBankAccount",
    "currency", "type", "modifiedDate", "companyId",
}

INVOICE_FIELDS = {
    "id", "issueDate", "dueDate", "currency", "amountDue",
    "totalAmount", "status", "modifiedDate", "companyId",
}

COMPANY_INFO_FIELDS = {
    "companyName", "registrationNumber", "currency", "companyId",
}

BILL_FIELDS = {
    "id", "reference", "supplierRef", "issueDate", "dueDate",
    "currency", "status", "totalAmount", "amountDue", "modifiedDate",
    "companyId",
}

CONNECTION_FIELDS = {
    "id", "integrationId", "sourceId", "platformName",
    "linkUrl", "status", "companyId",
}

EVENT_FIELDS = {
    "eventTimeUtc", "type", "description", "companyId",
}


class AllFieldsIntegrationTest(CodatBaseTest, unittest.TestCase):

    def setUp(self):
        self.ctx = self._create_context()
        self.ctx.catalog = self._make_selected_catalog()

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_sync_writes_records_for_streams_with_data(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Sync streams via sync() and verify records are written
        for streams that have mock data."""
        tap_codat.sync(self.ctx)

        written_streams = {
            call_args[0][0] for call_args in mock_write_records.call_args_list
        }

        # Streams with mock data should have records
        self.assertIn('companies', written_streams)
        self.assertIn('accounts', written_streams)
        self.assertIn('invoices', written_streams)
        self.assertIn('bills', written_streams)
        self.assertIn('company_info', written_streams)
        self.assertIn('events', written_streams)
        self.assertIn('balance_sheets', written_streams)
        self.assertIn('profit_and_loss', written_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_company_records_have_id(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Company records have the 'id' field."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'companies':
                for record in call_args[0][1]:
                    self.assertIn('id', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_account_records_have_required_fields(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Account records have companyId and id fields."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'accounts':
                for record in call_args[0][1]:
                    self.assertIn('id', record)
                    self.assertIn('companyId', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_invoice_records_have_required_fields(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Invoice records have companyId and id fields."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'invoices':
                for record in call_args[0][1]:
                    self.assertIn('id', record)
                    self.assertIn('companyId', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_company_info_records_have_company_id(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """company_info records have companyId."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'company_info':
                for record in call_args[0][1]:
                    self.assertIn('companyId', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_connection_records_have_required_fields(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Connection records have id and companyId."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'connections':
                for record in call_args[0][1]:
                    self.assertIn('id', record)
                    self.assertIn('companyId', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_events_records_have_required_fields(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Event records have eventTimeUtc and companyId."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'events':
                for record in call_args[0][1]:
                    self.assertIn('eventTimeUtc', record)
                    self.assertIn('companyId', record)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_sync_only_companies(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Sync only companies and verify only company records are written."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['companies'])

        tap_codat.sync(ctx)

        written_streams = {
            call_args[0][0] for call_args in mock_write_records.call_args_list
        }
        self.assertIn('companies', written_streams)
        self.assertNotIn('accounts', written_streams)
        self.assertNotIn('invoices', written_streams)

    # ------------------------------------------------------------------
    # Comprehensive field set validation (like taboola)
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_company_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Company records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'companies':
                record = call_args[0][1][0]
                self.assertTrue(
                    COMPANY_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {COMPANY_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No companies records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_account_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Account records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'accounts':
                record = call_args[0][1][0]
                self.assertTrue(
                    ACCOUNT_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {ACCOUNT_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No accounts records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_invoice_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Invoice records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'invoices':
                record = call_args[0][1][0]
                self.assertTrue(
                    INVOICE_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {INVOICE_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No invoices records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_company_info_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """company_info records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'company_info':
                record = call_args[0][1][0]
                self.assertTrue(
                    COMPANY_INFO_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {COMPANY_INFO_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No company_info records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_bill_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Bill records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'bills':
                record = call_args[0][1][0]
                self.assertTrue(
                    BILL_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {BILL_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No bills records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_connection_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Connection records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'connections':
                record = call_args[0][1][0]
                self.assertTrue(
                    CONNECTION_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {CONNECTION_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No connections records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.streams.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.singer.write_state")
    def test_all_event_fields_replicated(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Event records contain all expected fields."""
        tap_codat.sync(self.ctx)
        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'events':
                record = call_args[0][1][0]
                self.assertTrue(
                    EVENT_FIELDS.issubset(set(record.keys())),
                    f"Missing fields: {EVENT_FIELDS - set(record.keys())}",
                )
                return
        self.fail("No events records written")
