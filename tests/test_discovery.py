"""Integration test: discovery produces correct catalog and metadata."""
import unittest

try:
    from .base import CodatBaseTest
except ImportError:
    from base import CodatBaseTest

from singer import metadata


class DiscoveryIntegrationTest(CodatBaseTest, unittest.TestCase):

    def test_discovery_returns_all_expected_streams(self):
        """Verify discover() returns all expected streams."""
        catalog = self._run_discover()
        stream_ids = {entry.tap_stream_id for entry in catalog.streams}
        self.assertEqual(stream_ids, self.ALL_STREAM_IDS)

    def test_discovery_key_properties_match_expected(self):
        """Verify each stream has the expected primary keys."""
        catalog = self._run_discover()
        expected = self.expected_metadata()
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                root_meta = {}
                mdata = metadata.to_map(entry.metadata)
                root_meta = mdata.get((), {})
                actual_keys = set(root_meta.get('table-key-properties', []))
                self.assertEqual(
                    actual_keys,
                    expected[entry.tap_stream_id][self.PRIMARY_KEYS],
                )

    def test_discovery_schema_properties_exist(self):
        """Each stream schema has at least one property."""
        catalog = self._run_discover()
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema = entry.schema.to_dict()
                self.assertIn('properties', schema)
                self.assertTrue(len(schema['properties']) > 0)

    def test_discovery_key_properties_in_schema(self):
        """Key properties listed in metadata exist in the schema."""
        catalog = self._run_discover()
        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema_props = set(entry.schema.to_dict().get('properties', {}).keys())
                key_props = set(entry.key_properties or [])
                self.assertTrue(
                    key_props.issubset(schema_props),
                    f"key_properties {key_props} not in schema {schema_props}",
                )
