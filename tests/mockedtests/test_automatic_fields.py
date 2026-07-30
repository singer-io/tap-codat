"""Integration test: automatic fields — all fields are marked as
inclusion=automatic in metadata (codat marks every field as automatic)."""
import unittest

from singer import metadata

try:
    from .base import CodatBaseTest
except ImportError:
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    from base import CodatBaseTest


class AutomaticFieldsIntegrationTest(CodatBaseTest, unittest.TestCase):

    def test_all_fields_are_automatic(self):
        """Verify that all fields in every stream are marked as
        inclusion=automatic in discovery metadata."""
        catalog = self._run_discover()

        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                mdata = metadata.to_map(entry.metadata)
                schema_props = set(
                    entry.schema.to_dict().get('properties', {}).keys()
                )

                for field_name in schema_props:
                    breadcrumb = ('properties', field_name)
                    inclusion = mdata.get(breadcrumb, {}).get('inclusion')
                    self.assertEqual(
                        inclusion,
                        'automatic',
                        f"Stream '{entry.tap_stream_id}', field '{field_name}' "
                        f"has inclusion '{inclusion}' instead of 'automatic'",
                    )

    def test_primary_keys_are_in_schema(self):
        """Verify that all primary key fields exist in the schema properties."""
        catalog = self._run_discover()
        expected = self.expected_metadata()

        for entry in catalog.streams:
            with self.subTest(stream=entry.tap_stream_id):
                schema_props = set(
                    entry.schema.to_dict().get('properties', {}).keys()
                )
                pk_fields = expected[entry.tap_stream_id][self.PRIMARY_KEYS]

                self.assertTrue(
                    pk_fields.issubset(schema_props),
                    f"Stream '{entry.tap_stream_id}': PK fields {pk_fields} "
                    f"not in schema properties {schema_props}",
                )
