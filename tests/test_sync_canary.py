"""Integration test: basic sync canary — verify the full pipeline runs
and emits records for expected streams."""
import unittest
from unittest.mock import patch

import tap_codat

try:
    from .base import CodatBaseTest
except ImportError:
    from base import CodatBaseTest


class SyncCanaryIntegrationTest(CodatBaseTest, unittest.TestCase):

    def setUp(self):
        self.ctx = self._create_context()
        self.ctx.catalog = self._make_selected_catalog()

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_full_pipeline_emits_records(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Smoke test — run the full sync pipeline and verify
        at least one record batch is written."""
        tap_codat.sync(self.ctx)

        self.assertTrue(mock_write_records.called)
        written_streams = {
            call_args[0][0] for call_args in mock_write_records.call_args_list
        }
        # Companies should always be written
        self.assertIn('companies', written_streams)

    @patch("tap_codat.streams.singer.write_records")
    @patch("tap_codat.state.singer.write_state")
    @patch("tap_codat.singer.write_schema")
    @patch("tap_codat.context.singer.write_state")
    def test_schemas_emitted_for_synced_streams(
        self, mock_ctx_write_state, mock_write_schema,
        mock_stream_write_state, mock_write_records,
    ):
        """Verify write_schema is called for synced streams."""
        tap_codat.sync(self.ctx)

        schema_streams = {
            call_args[0][0] for call_args in mock_write_schema.call_args_list
        }
        # At minimum, companies schema must be emitted
        self.assertIn('companies', schema_streams)
