"""Unit tests for tap_codat.transform — DictKey, ListItems, find_dt_paths,
safe_strftime, _transform_impl, and transform_dts."""

import unittest
from unittest.mock import MagicMock, patch

import pendulum

from tap_codat.transform import (
    DictKey,
    ListItems,
    TransformationException,
    _check_type,
    _transform_impl,
    find_dt_paths,
    safe_strftime,
    transform_dts,
)


# ---------------------------------------------------------------------------
# DictKey
# ---------------------------------------------------------------------------

class TestDictKey(unittest.TestCase):

    def test_repr(self):
        dk = DictKey("created")
        self.assertEqual(repr(dk), "<DictKey(created)>")

    def test_equality_same_key(self):
        self.assertEqual(DictKey("a"), DictKey("a"))

    def test_inequality_different_key(self):
        self.assertNotEqual(DictKey("a"), DictKey("b"))

    def test_expected_type_is_dict(self):
        self.assertEqual(DictKey.expected_type, dict)

    def test_iterate_yields_key_value(self):
        dk = DictKey("name")
        item = {"name": "Alice", "age": 30}
        pairs = list(dk.iterate(item))
        self.assertEqual(pairs, [("name", "Alice")])

    def test_iterate_missing_key(self):
        dk = DictKey("missing")
        item = {"name": "Alice"}
        pairs = list(dk.iterate(item))
        self.assertEqual(pairs, [("missing", None)])


# ---------------------------------------------------------------------------
# ListItems
# ---------------------------------------------------------------------------

class TestListItems(unittest.TestCase):

    def test_repr(self):
        self.assertEqual(repr(ListItems), "<ListItems>")

    def test_expected_type_is_list(self):
        self.assertEqual(ListItems.expected_type, list)

    def test_iterate_yields_index_value(self):
        items = ["a", "b", "c"]
        pairs = list(ListItems.iterate(items))
        self.assertEqual(pairs, [(0, "a"), (1, "b"), (2, "c")])

    def test_iterate_empty_list(self):
        pairs = list(ListItems.iterate([]))
        self.assertEqual(pairs, [])

    def test_iterate_single_element(self):
        pairs = list(ListItems.iterate(["only"]))
        self.assertEqual(pairs, [(0, "only")])


# ---------------------------------------------------------------------------
# _check_type
# ---------------------------------------------------------------------------

class TestCheckType(unittest.TestCase):

    def test_dict_passes_for_dict(self):
        # Should not raise
        _check_type({"key": "val"}, [DictKey("key")], 0)

    def test_list_passes_for_list_items(self):
        _check_type([1, 2], [ListItems], 0)

    def test_raises_for_wrong_type_dict_expected(self):
        with self.assertRaises(TransformationException):
            _check_type("not a dict", [DictKey("key")], 0)

    def test_raises_for_wrong_type_list_expected(self):
        with self.assertRaises(TransformationException):
            _check_type({"key": "val"}, [ListItems], 0)


# ---------------------------------------------------------------------------
# TransformationException
# ---------------------------------------------------------------------------

class TestTransformationException(unittest.TestCase):

    def test_message_contains_type_info(self):
        exc = TransformationException("hello", [DictKey("x")], 0)
        self.assertIn("str", str(exc))
        self.assertIn("path", str(exc))


# ---------------------------------------------------------------------------
# find_dt_paths
# ---------------------------------------------------------------------------

class TestFindDtPaths(unittest.TestCase):

    def _schema(self, fmt=None, properties=None, items=None):
        s = MagicMock()
        s.format = fmt
        s.properties = properties
        s.items = items
        return s

    def test_datetime_at_root(self):
        result = find_dt_paths(self._schema(fmt="date-time"))
        self.assertEqual(result, [[]])

    def test_non_datetime_returns_empty(self):
        result = find_dt_paths(self._schema())
        self.assertEqual(result, [])

    def test_nested_property(self):
        child = self._schema(fmt="date-time")
        parent = self._schema(properties={"created": child})
        result = find_dt_paths(parent)
        self.assertEqual(result, [[DictKey("created")]])

    def test_array_items(self):
        item = self._schema(fmt="date-time")
        parent = self._schema(items=item)
        result = find_dt_paths(parent)
        self.assertEqual(result, [[ListItems]])

    def test_multiple_dt_fields(self):
        dt1 = self._schema(fmt="date-time")
        dt2 = self._schema(fmt="date-time")
        non_dt = self._schema()
        parent = self._schema(properties={"a": dt1, "b": non_dt, "c": dt2})
        result = find_dt_paths(parent)
        self.assertEqual(len(result), 2)
        paths_as_keys = {r[0].key for r in result}
        self.assertEqual(paths_as_keys, {"a", "c"})

    def test_deeply_nested(self):
        leaf = self._schema(fmt="date-time")
        mid = self._schema(properties={"ts": leaf})
        root = self._schema(properties={"inner": mid})
        result = find_dt_paths(root)
        self.assertEqual(result, [[DictKey("inner"), DictKey("ts")]])

    def test_array_of_objects_with_dt(self):
        dt = self._schema(fmt="date-time")
        obj = self._schema(properties={"date": dt})
        arr = self._schema(items=obj)
        root = self._schema(properties={"events": arr})
        result = find_dt_paths(root)
        self.assertEqual(result, [[DictKey("events"), ListItems, DictKey("date")]])


# ---------------------------------------------------------------------------
# safe_strftime
# ---------------------------------------------------------------------------

class TestSafeStrftime(unittest.TestCase):

    def test_standard_datetime(self):
        dt = pendulum.parse("2024-06-15T10:30:00Z")
        result = safe_strftime(dt)
        self.assertIn("2024", result)
        self.assertIn("06", result)
        self.assertIn("15", result)

    def test_returns_string(self):
        dt = pendulum.parse("2023-01-01T00:00:00Z")
        self.assertIsInstance(safe_strftime(dt), str)

    def test_midnight(self):
        dt = pendulum.parse("2024-12-31T00:00:00Z")
        result = safe_strftime(dt)
        self.assertIn("2024-12-31", result)

    def test_includes_time_component(self):
        dt = pendulum.parse("2024-03-15T14:30:45Z")
        result = safe_strftime(dt)
        self.assertIn("14:30:45", result)

    @patch("tap_codat.transform.singer_strftime", return_value="4Y-01-01 00:00:00")
    def test_fallback_for_broken_strftime_impl(self, _mock_strftime):
        dt = pendulum.parse("2024-03-15T14:30:45Z")
        result = safe_strftime(dt)
        self.assertEqual(result, dt.strftime('%Y-%m-%dT%H:%M:%S.%fZ'))


# ---------------------------------------------------------------------------
# _transform_impl
# ---------------------------------------------------------------------------

class TestTransformImpl(unittest.TestCase):

    def test_returns_falsy_item_unchanged(self):
        self.assertIsNone(_transform_impl(None, [DictKey("x")]))
        self.assertEqual(_transform_impl("", [DictKey("x")]), "")
        self.assertEqual(_transform_impl(0, [DictKey("x")]), 0)
        self.assertEqual(_transform_impl([], [DictKey("x")]), [])

    def test_transforms_datetime_at_leaf(self):
        result = _transform_impl("2024-01-15T10:00:00.00Z", [], 0)
        self.assertIn("2024-01-15", result)

    def test_transforms_nested_dict(self):
        item = {"date": "2024-06-15T10:00:00.00Z"}
        result = _transform_impl(item, [DictKey("date")])
        self.assertIn("2024-06-15", result["date"])

    def test_skips_none_values(self):
        item = {"date": None, "name": "test"}
        result = _transform_impl(item, [DictKey("date")])
        self.assertIsNone(result["date"])
        self.assertEqual(result["name"], "test")


# ---------------------------------------------------------------------------
# transform_dts
# ---------------------------------------------------------------------------

class TestTransformDts(unittest.TestCase):

    def test_transforms_datetime_field(self):
        records = [{"date": "2024-06-15T10:00:00.00Z", "name": "test"}]
        paths = [[DictKey("date")]]
        result = transform_dts(records, paths)
        self.assertIn("2024-06-15", result[0]["date"])
        self.assertEqual(result[0]["name"], "test")

    def test_leaves_non_dt_fields_unchanged(self):
        records = [{"name": "test", "value": 42}]
        result = transform_dts(records, [])
        self.assertEqual(result[0]["name"], "test")
        self.assertEqual(result[0]["value"], 42)

    def test_empty_records(self):
        result = transform_dts([], [[DictKey("date")]])
        self.assertEqual(result, [])

    def test_multiple_paths(self):
        records = [{"created": "2024-01-01T00:00:00.00Z", "modified": "2024-06-15T00:00:00.00Z"}]
        paths = [[DictKey("created")], [DictKey("modified")]]
        result = transform_dts(records, paths)
        self.assertIn("2024-01-01", result[0]["created"])
        self.assertIn("2024-06-15", result[0]["modified"])

    def test_multiple_records(self):
        records = [
            {"date": "2024-01-01T00:00:00.00Z"},
            {"date": "2024-06-15T00:00:00.00Z"},
        ]
        paths = [[DictKey("date")]]
        result = transform_dts(records, paths)
        self.assertIn("2024-01-01", result[0]["date"])
        self.assertIn("2024-06-15", result[1]["date"])

    def test_nested_datetime_in_array(self):
        records = [{"events": [{"ts": "2024-03-01T12:00:00.00Z"}]}]
        paths = [[DictKey("events"), ListItems, DictKey("ts")]]
        result = transform_dts(records, paths)
        self.assertIn("2024-03-01", result[0]["events"][0]["ts"])

    def test_preserves_non_datetime_in_mixed_record(self):
        records = [{"date": "2024-01-01T00:00:00.00Z", "count": 5, "active": True}]
        paths = [[DictKey("date")]]
        result = transform_dts(records, paths)
        self.assertEqual(result[0]["count"], 5)
        self.assertTrue(result[0]["active"])


if __name__ == "__main__":
    unittest.main()
