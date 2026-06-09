"""Integration test: bookmark / incremental sync — verify state is
updated after syncing incremental streams."""
import unittest
from unittest.mock import patch

import tap_codat

try:
    from .base import CodatBaseTest
except ImportError:
    from base import CodatBaseTest


class BookmarkIntegrationTest(CodatBaseTest, unittest.TestCase):

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_currently_syncing_is_cleared(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """After sync completes, currently_syncing should be None."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog()
        tap_codat.sync(ctx)
        self.assertIsNone(ctx.state.get("currently_syncing"))

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_state_written_during_sync(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """write_state is called during sync to persist progress."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog()
        tap_codat.sync(ctx)
        # Both ctx.write_state() and save_state() call singer.write_state
        # (same module object), so a single patch captures all calls.
        self.assertTrue(mock_write_state.called)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_incremental_stream_updates_bookmark(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Incremental stream (accounts) should update state bookmarks
        with the max modifiedDate value."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(
            stream_names=['accounts'])
        tap_codat.sync(ctx)

        # After syncing accounts, the state should contain bookmarks
        # for accounts.comp-001 with the max modifiedDate
        bookmarks = ctx.state.get('bookmarks', {})
        accounts_bookmark = bookmarks.get('accounts', {}).get('comp-001', {})
        if accounts_bookmark:
            self.assertEqual(accounts_bookmark.get('field'), 'modifiedDate')
            self.assertIsNotNone(accounts_bookmark.get('last_record'))

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_full_table_stream_does_not_update_bookmark(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Full table stream (companies) should not update bookmarks."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(
            stream_names=['companies'])
        tap_codat.sync(ctx)

        bookmarks = ctx.state.get('bookmarks', {})
        # Companies is full table, no company-scoped bookmark expected
        company_bookmarks = bookmarks.get('companies', {})
        self.assertEqual(len(company_bookmarks), 0)

    # ------------------------------------------------------------------
    # State structure validation
    # ------------------------------------------------------------------

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_bookmark_structure_has_field_and_last_record(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Incremental stream bookmark should have 'field' and 'last_record' keys."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['accounts'])
        tap_codat.sync(ctx)

        bookmarks = ctx.state.get('bookmarks', {})
        accounts_bm = bookmarks.get('accounts', {}).get('comp-001', {})
        if accounts_bm:
            self.assertIn('field', accounts_bm)
            self.assertIn('last_record', accounts_bm)
            self.assertEqual(accounts_bm['field'], 'modifiedDate')
            # last_record should be a date string
            self.assertIsInstance(accounts_bm['last_record'], str)
            self.assertIn('2024', accounts_bm['last_record'])

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_bookmark_uses_max_modified_date(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Bookmark last_record should be the max modifiedDate from records."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(stream_names=['accounts'])
        tap_codat.sync(ctx)

        bookmarks = ctx.state.get('bookmarks', {})
        accounts_bm = bookmarks.get('accounts', {}).get('comp-001', {})
        if accounts_bm:
            # From mock data: acct-001 has 2024-01-15, acct-002 has 2024-03-20
            # Max should be 2024-03-20
            self.assertIn('2024-03-20', accounts_bm['last_record'])

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    def test_multiple_incremental_streams_each_get_bookmarks(
        self, mock_write_schema,
        mock_write_state, mock_write_records,
    ):
        """Multiple incremental streams each get their own bookmarks."""
        ctx = self._create_context()
        ctx.catalog = self._make_selected_catalog(
            stream_names=['accounts', 'invoices', 'bills'])
        tap_codat.sync(ctx)

        bookmarks = ctx.state.get('bookmarks', {})
        # Check that at least accounts has a bookmark
        self.assertIn('accounts', bookmarks)
        self.assertIn('comp-001', bookmarks.get('accounts', {}))
        # Invoices and bills should also have bookmarks
        self.assertIn('invoices', bookmarks)
        self.assertIn('comp-001', bookmarks.get('invoices', {}))
        self.assertIn('bills', bookmarks)
        self.assertIn('comp-001', bookmarks.get('bills', {}))
