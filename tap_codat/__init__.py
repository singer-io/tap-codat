#!/usr/bin/env python3
import os
import json
import singer
from singer import utils, metadata
from singer.catalog import Catalog, CatalogEntry, Schema
from . import streams as streams_
from .context import Context

REQUIRED_CONFIG_KEYS = ["start_date", "api_key"]
LOGGER = singer.get_logger()


def get_abs_path(path):
    return os.path.join(os.path.dirname(os.path.realpath(__file__)), path)


def load_schema(ctx, tap_stream_id):
    path = "schemas/{}.json".format(tap_stream_id)
    schema = utils.load_json(get_abs_path(path))
    dependencies = schema.pop("tap_schema_dependencies", [])
    refs = {}
    for sub_stream_id in dependencies:
        refs[sub_stream_id] = load_schema(ctx, sub_stream_id)
    if refs:
        singer.resolve_schema_references(schema, refs)
    return schema


def load_and_write_schema(ctx, stream):
    singer.write_schema(
        stream.tap_stream_id,
        load_schema(ctx, stream.tap_stream_id),
        stream.pk_fields,
    )

    for substream in stream.substreams:
        load_and_write_schema(ctx, substream)


def check_credentials_are_authorized(ctx):
    streams_.companies.raw_fetch(ctx)


def add_stream_to_catalog(catalog, ctx, stream):
    schema_dict = load_schema(ctx, stream.tap_stream_id)
    schema = Schema.from_dict(schema_dict)
    mdata = metadata.get_standard_metadata(schema_dict,
                                           key_properties=stream.pk_fields)
    mdata = metadata.to_map(mdata)

    for field_name in schema_dict['properties'].keys():
        mdata = metadata.write(mdata, ('properties', field_name), 'inclusion', 'automatic')

    catalog.streams.append(CatalogEntry(
        stream=stream.tap_stream_id,
        tap_stream_id=stream.tap_stream_id,
        key_properties=stream.pk_fields,
        schema=schema,
        metadata=metadata.to_list(mdata)
    ))


def discover(ctx):
    check_credentials_are_authorized(ctx)
    catalog = Catalog([])

    for stream in streams_.all_streams:
        add_stream_to_catalog(catalog, ctx, stream)
        for substream in stream.substreams:
            add_stream_to_catalog(catalog, ctx, substream)

    return catalog


def sync(ctx):
    streams_.companies.fetch_into_cache(ctx)
    currently_syncing = ctx.state.get("currently_syncing")
    start_idx = streams_.all_stream_ids.index(currently_syncing) \
        if currently_syncing else 0
    streams = [s for s in streams_.all_streams[start_idx:]
               if s.tap_stream_id in ctx.selected_stream_ids]
    for stream in streams:
        ctx.state["currently_syncing"] = stream.tap_stream_id
        ctx.write_state()
        load_and_write_schema(ctx, stream)
        stream.sync(ctx)
    ctx.state["currently_syncing"] = None
    ctx.write_state()


def main_impl():
    args = utils.parse_args(REQUIRED_CONFIG_KEYS)
    ctx = Context(args.config, args.state)
    if args.discover:
        discover(ctx).dump()
        print()
    else:
        ctx.catalog = Catalog.from_dict(args.properties) \
            if args.properties else discover(ctx)
        sync(ctx)
        ctx.dump_logs()


def main():
    try:
        main_impl()
    except Exception as exc:
        LOGGER.critical(exc)
        raise

if __name__ == "__main__":
    main()
