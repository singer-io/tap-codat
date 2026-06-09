"""Integration test: pagination — verify the tap handles paginated
streams correctly with mocked API responses."""
import unittest
from unittest.mock import patch

import tap_codat

try:
    from .base import CodatBaseTest
except ImportError:
    from base import CodatBaseTest


class PaginationIntegrationTest(CodatBaseTest, unittest.TestCase):

    def setUp(self):
        self.ctx = self._create_context()
        self.ctx.catalog = self._make_selected_catalog()

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_all_accounts_returned_in_single_page(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Verify all accounts are written when the API returns them
        in a single page (fewer than PAGE_SIZE records)."""
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
    def test_all_invoices_returned_in_single_page(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Verify all invoices are written when the API returns them
        in a single page."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'invoices':
                records = call_args[0][1]
                self.assertEqual(len(records), len(self.MOCK_INVOICES))
                return
        self.fail("No invoices records written")

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_all_bills_returned_in_single_page(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Verify all bills are written when the API returns them
        in a single page."""
        tap_codat.sync(self.ctx)

        for call_args in mock_write_records.call_args_list:
            if call_args[0][0] == 'bills':
                records = call_args[0][1]
                self.assertEqual(len(records), len(self.MOCK_BILLS))
                return
        self.fail("No bills records written")
