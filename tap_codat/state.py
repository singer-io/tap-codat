import json
import singer

from dateutil.parser import parse

LOGGER = singer.get_logger()


def get_last_record_value_for_table(state, table, company_id):
    company_bookmark = (state.get('bookmarks', {})
                             .get(table, {})
                             .get(company_id))
    if not isinstance(company_bookmark, dict):
        return None

    last_value = company_bookmark.get('last_record')

    if last_value is None:
        return None

    return parse(last_value)


def incorporate(state, table, company_id, field, value):
    if value is None:
        return state

    new_state = state.copy()

    parsed = parse(value).strftime("%Y-%m-%dT%H:%M:%SZ")

    if 'bookmarks' not in new_state:
        new_state['bookmarks'] = {}

    if table not in new_state['bookmarks']:
        new_state['bookmarks'][table] = {}

    # Sanitize first: remove any pre-existing empty dict or null company
    _sanitize_stream_bookmark(new_state, table)

    if table not in new_state['bookmarks']:
        new_state['bookmarks'][table] = {}

    current_value = (new_state['bookmarks'].get(table, {})
                     .get(company_id) or {}).get('last_record')
    if current_value is None or current_value < parsed:
        new_state['bookmarks'][table][company_id] = {
            'field': field,
            'last_record': parsed,
        }

    return new_state


def _sanitize_stream_bookmark(state, table):
    """Remove any empty dict ({}) or null company entries from a specific
    stream bookmark, and remove the stream key itself if it ends up empty."""
    bookmarks = state.get('bookmarks')
    if not isinstance(bookmarks, dict):
        return

    stream_val = bookmarks.get(table)
    if not isinstance(stream_val, dict):
        return

    bad_keys = [cid for cid, cval in stream_val.items()
                if cval is None or cval == {}]
    for cid in bad_keys:
        del stream_val[cid]

    if not stream_val:
        del bookmarks[table]


def sanitize_bookmarks(state):
    """Sanitize all stream bookmarks by removing any empty dict ({}) or
    null company entries. Prevents emitting bad state shapes like:

        {"bookmarks": {"companies": {"{ID}": {}}}}   # BAD
        {"bookmarks": {"companies": {"{ID}": null}}} # BAD
    """
    bookmarks = state.get('bookmarks')
    if not isinstance(bookmarks, dict):
        return state

    for table in list(bookmarks.keys()):
        _sanitize_stream_bookmark(state, table)

    return state


def save_state(state):
    if not state:
        return

    LOGGER.info('Updating state.')

    singer.write_state(state)


def load_state(filename):
    if filename is None:
        return {}

    try:
        with open(filename) as handle:
            return json.load(handle)
    except:
        LOGGER.fatal("Failed to decode state file. Is it valid json?")
        raise RuntimeError
