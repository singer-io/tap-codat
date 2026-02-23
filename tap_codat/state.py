import json
import singer

from dateutil.parser import parse

LOGGER = singer.get_logger()


def get_last_record_value_for_table(state, table, company_id):
    last_value = (state.get('bookmarks', {})
                      .get(table, {})
                      .get(company_id) or {})\
                      .get('last_record')

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

    current_value = new_state['bookmarks'].get(table, {}).get(company_id, {}).get('last_record')
    if current_value is None or current_value < parsed:
        new_state['bookmarks'][table][company_id] = {
            'field': field,
            'last_record': parsed,
        }

    return new_state


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
