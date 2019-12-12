import singer
from singer import metrics
from singer.transform import transform as tform
from .transform import transform_dts
import json

from tap_codat.state import incorporate, save_state, \
    get_last_record_value_for_table

from contextlib import ContextDecorator

LOGGER = singer.get_logger()
PAGE_SIZE = 500


class capture_state(ContextDecorator):
    def __init__(self, ctx, stream_id, field_name, company_id):
        self.field_name = field_name
        self.stream_id = stream_id
        self.ctx = ctx
        self.company_id = company_id
        self.max = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        if self.field_name and self.max is not None:
            company_stream = "{}.{}".format(self.stream_id, self.company_id)
            self.ctx.state = incorporate(self.ctx.state,
                                         company_stream,
                                         self.field_name,
                                         self.max)
            save_state(self.ctx.state)

    def get_max(self):
        company_stream = "{}.{}".format(self.stream_id, self.company_id)
        state_dt = get_last_record_value_for_table(self.ctx.state, company_stream)
        if state_dt:
            return state_dt.strftime('%Y-%m-%dT%H:%M:%S.00Z')
        else:
            return self.ctx.config.get('start_date')

    def update(self, records):
        if self.field_name is None:
            return

        for record in records:
            if self.field_name not in record:
                continue

            new_value = record[self.field_name]
            if self.max is None or new_value > self.max:
                self.max = new_value


class Stream(object):
    def __init__(self, tap_stream_id, pk_fields, path,
                 returns_collection=True,
                 collection_key=None,
                 custom_formatter=None,
                 substreams=None,
                 state_filter=None):
        self.tap_stream_id = tap_stream_id
        self.pk_fields = pk_fields
        self.path = path
        self.returns_collection = returns_collection
        self.collection_key = collection_key
        self.custom_formatter = custom_formatter or (lambda x: x)

        if substreams is not None:
            self.substreams = substreams
        else:
            self.substreams = []

        self.state_filter = state_filter

    def metrics(self, records):
        with metrics.record_counter(self.tap_stream_id) as counter:
            counter.increment(len(records))

    def write_records(self, records):
        # Debugging for extra long lines that exceed the Stitch
        # maximum record size (4 mb)
        for record in records:
            asjson = json.dumps(record)
            length = len(asjson)
            max_length = 4*1024*1024
            if length > max_length:
                record_id = record.get('id', 'unknown')
                LOGGER.info("I saw record that was {} bytes ({})".format(
                    length, record_id))

        singer.write_records(self.tap_stream_id, records)
        self.metrics(records)

    def log_additional_properties(self, ctx, records):
        schema = ctx.catalog.get_stream(self.tap_stream_id).schema.to_dict()
        logged_error = False

        # Try to transform this record according to the specified schema. Any
        # fields which are present in the data but absent from the schema
        # will be logged below. As the Codat API matures, additionalProperties
        # should be changed to `false` everywhere, and this code should be removed.
        for record in records:
            try:
                tform(record, schema)
            except Exception as e:
                if not logged_error:
                    error_snippet = str(e)[:1024]
                    LOGGER.info("Ignoring validation error: {}".format(error_snippet))

    def format_response(self, response, company, extras=None):
        if self.returns_collection:
            if self.collection_key:
                records = (response or {}).get(self.collection_key, [])
            else:
                records = response or []
        elif isinstance(response, list):
            records = response
        else:
            records = [] if not response else [response]
        for record in records:
            record["companyId"] = company["id"]
            if extras is not None:
                record.update(extras)
        return self.custom_formatter(records)

    def transform_dts(self, ctx, records):
        transformed = transform_dts(records, ctx.schema_dt_paths[self.tap_stream_id])
        self.log_additional_properties(ctx, transformed)
        return transformed


class Companies(Stream):
    def raw_fetch(self, ctx):
        return ctx.client.GET({"path": self.path}, self.tap_stream_id)

    def fetch_into_cache(self, ctx):
        resp = self.raw_fetch(ctx)
        ctx.cache["companies"] = self.transform_dts(ctx, resp["companies"])

    def sync(self, ctx):
        self.write_records(ctx.cache["companies"])


class Basic(Stream):
    def sync(self, ctx):
        for i, company in enumerate(ctx.cache["companies"]):
            LOGGER.info("Syncing {} for Company {} of {}".format(
                self.tap_stream_id,
                i + 1,
                len(ctx.cache['companies'])
            ))

            self.sync_for_company(ctx, company)

    def sync_for_company(self, ctx, company):
        with capture_state(
            ctx,
            self.tap_stream_id,
            self.state_filter,
            company['id']
        ) as sync:
            path = self.path.format(companyId=company["id"])
            params = self.get_params(ctx, sync)
            resp = ctx.client.GET({"path": path, "params": params}, self.tap_stream_id)
            records = self.transform_dts(ctx, self.format_response(resp, company))

            for stream in self.substreams:
                stream.sync_children(ctx, path, company, records)

            sync.update(records)
            self.write_records(records)

    def get_incremental_filter(self, ctx, sync):
        max_dt = sync.get_max()
        if max_dt and self.state_filter is not None:
            return {
                "query": "{}>{}".format(self.state_filter, max_dt)
            }
        else:
            return {}

    def get_params(self, ctx, sync):
        return self.get_incremental_filter(ctx, sync)


class BankStatementLines(Basic):
    def sync_children(self, ctx, parent_path, company, bank_statements):
        for i, bank_statement in enumerate(bank_statements):
            LOGGER.info("Syncing {} for Bank Statement {} of {}".format(
                self.tap_stream_id,
                i + 1,
                len(bank_statements)
            ))


            lines = bank_statement.pop('details', [])
            self.sync_lines_for_statement(ctx, company, bank_statement, lines)

    def sync_lines_for_statement(self, ctx, company, bank_statement, lines):
        for i, line in enumerate(lines):
            line['companyId'] = company['id']
            line['accountName'] = bank_statement['accountName']
            line['_lineIndex'] = i

        self.write_records(lines)


class BankAccountTransactions(Basic):
    def sync_children(self, ctx, parent_path, company, bank_accounts):
        for i, bank_account in enumerate(bank_accounts):
            LOGGER.info("Syncing {} for Bank Account {} of {}".format(
                self.tap_stream_id,
                i + 1,
                len(bank_accounts)
            ))

            self.sync_transactions_for_account(ctx, parent_path, company, bank_account)

    def sync_transactions_for_account(self, ctx, parent_path, company, bank_account):
        if 'id' not in bank_account:
            return

        path = parent_path + self.path.format(**bank_account)
        resp = ctx.client.GET({"path": path}, self.tap_stream_id)

        if resp is None:
            return

        transactions = self.transform_dts(ctx, resp)
        for i, transaction in enumerate(transactions):
            transaction['companyId'] = company['id']
            transaction['bankAccountId'] = bank_account['id']
            transaction['_transactionIndex'] = i

        self.write_records(transactions)


class Events(Basic):
    def get_params(self, ctx, sync):
        max_dt = sync.get_max()
        if max_dt:
            return {
                "fromDate": max_dt
            }
        else:
            return {}

    def sync_for_company(self, ctx, company):
        with capture_state(
            ctx,
            self.tap_stream_id,
            "eventTimeUtc",
            company['id']
        ) as sync:
            path = self.path.format(companyId=company["id"])
            params = self.get_params(ctx, sync)
            resp = ctx.client.GET({"path": path, "params": params}, self.tap_stream_id)
            records = self.transform_dts(ctx, self.format_response(resp, company))
            sync.update(records)
            self.write_records(records)


class Paginated(Basic):
    def sync_for_company(self, ctx, company):
        with capture_state(
            ctx,
            self.tap_stream_id,
            self.state_filter,
            company['id']
        ) as sync:
            path = self.path.format(companyId=company["id"])
            page = 1
            while True:
                LOGGER.info("Syncing page {} for {} stream (company={})".format(
                    page,
                    self.tap_stream_id,
                    company['id']
                ))
                params = self.get_params(ctx, sync, page)
                resp = ctx.client.GET({"path": path, "params": params}, self.tap_stream_id)
                records = self.transform_dts(ctx, self.format_response(resp, company))
                sync.update(records)
                self.write_records(records)
                if len(records) < PAGE_SIZE:
                    break
                page += 1

    def get_params(self, ctx, sync, page):
        incremental_params = self.get_incremental_filter(ctx, sync)
        params = {
            "pageSize": PAGE_SIZE,
            "page": page,
            "orderBy": self.state_filter
        }
        params.update(incremental_params)
        return params


class BankAccounts(Paginated):
    def sync_for_company(self, ctx, company):
        with capture_state(
            ctx,
            self.tap_stream_id,
            self.state_filter,
            company['id']
        ) as sync:
            for conn in company.get('dataConnections', []):
                connId = conn.get('id')
                if not connId:
                    continue
                path = self.path.format(companyId=company["id"], connectionId=connId)
                page = 1
                while True:
                    LOGGER.info("Syncing page {} for {} stream (company={}, conn={})".format(
                        page,
                        self.tap_stream_id,
                        company['id'],
                        connId
                    ))
                    params = self.get_params(ctx, sync, page)
                    resp = ctx.client.GET({"path": path, "params": params}, self.tap_stream_id)
                    records = self.transform_dts(ctx, self.format_response(resp, company, {
                        "connectionId": connId
                    }))
                    sync.update(records)
                    self.write_records(records)
                    if len(records) < PAGE_SIZE:
                        break
                    page += 1


class Financials(Basic):
    def sync_for_company(self, ctx, company):
        path = self.path.format(companyId=company["id"])
        params = {
            "periodLength": ctx.config.get("financials_period_length", 1),
            "periodsToCompare": ctx.config.get("financials_periods_to_compare", 24),
        }
        resp = ctx.client.GET({"path": path, "params": params}, self.tap_stream_id)
        records = self.transform_dts(ctx, self.format_response(resp, company))
        self.write_records(records)


def flatten_report(item, parent_names=[]):
    item_tformed = {
        "name": item["name"],
        "value": item["value"],
        "accountId": item.get("accountId", None),
    }
    for idx, parent_name in enumerate(parent_names):
        item_tformed["name_" + str(idx)] = parent_name
    item_tformed["name_" + str(len(parent_names))] = item["name"]
    results = [item_tformed]
    sub_parent_names = parent_names + [item["name"]]
    for sub_item in item.get("items", []):
        results += flatten_report(sub_item, sub_parent_names)
    return results


def _update(dict_, key, function):
    dict_[key] = function(dict_[key])


def flatten_balance_sheets(balance_sheets):
    for balance_sheet in balance_sheets:
        for report in balance_sheet["reports"]:
            for key in ["assets", "liabilities", "equity"]:
                _update(report, key, flatten_report)
    return balance_sheets


def flatten_profit_and_loss(pnls):
    for pnl in pnls:
        for report in pnl["reports"]:
            for key in ["otherExpenses", "expenses", "costOfSales",
                        "otherIncome", "income"]:
                _update(report, key, flatten_report)
    return pnls


def trunc_payment_allocation_notes(invoices):
    for invoice in invoices:
        payment_allocations = invoice.get('paymentAllocations', [])
        for allocation in payment_allocations:
            note = allocation.get('note')
            if isinstance(note, str) and len(note) > 1024:
                allocation['note'] = note[0:1024]

    return invoices


companies = Companies("companies", ["id"], "/companies")
all_streams = [
    companies,
    Basic("accounts",
          ["id", "companyId"],
          "/companies/{companyId}/data/accounts",
          collection_key="accounts",
          state_filter="modifiedDate"),
    BankAccounts("bank_accounts",
          ["accountName", "companyId", "connectionId"],
          "/companies/{companyId}/connections/{connectionId}/data/bankAccounts",
          collection_key='results',
          substreams=[BankAccountTransactions(
              "bank_account_transactions",
              ["companyId", "bankAccountId", "_transactionIndex"],
              "/{id}/transactions",
              returns_collection=False)]),
    Basic("bank_statements",
          ["accountName", "companyId"],
          "/companies/{companyId}/data/bankStatements",
          state_filter="modifiedDate",
          substreams=[BankStatementLines(
              "bank_statement_lines",
              ["companyId", "accountName", "_lineIndex"],
              None)]),
    Basic("bills",
          ["id", "companyId"],
          "/companies/{companyId}/data/bills",
          collection_key="bills",
          state_filter="modifiedDate"),
    Basic("company_info",
          ["companyId"],
          "/companies/{companyId}/data/info",
          returns_collection=False),  # Not filterable
    Basic("credit_notes",
          ["id", "companyId"],
          "/companies/{companyId}/data/creditNotes",
          collection_key="creditNotes",
          state_filter="modifiedDate"),
    Basic("customers",
          ["id", "companyId"],
          "/companies/{companyId}/data/customers",
          collection_key="customers",
          state_filter="modifiedDate"),
    Basic("payments",
          ["id", "companyId"],
          "/companies/{companyId}/data/payments",
          collection_key="payments",
          state_filter="modifiedDate"),
    Basic("suppliers",
          ["id", "companyId"],
          "/companies/{companyId}/data/suppliers",
          collection_key="suppliers",
          state_filter="modifiedDate"),
    Basic("connections",
          ["id", "companyId"],
          "/companies/{companyId}/connections",
          returns_collection=False),
    Paginated("bill_payments",
              ["id", "companyId"],
              "/companies/{companyId}/data/billpayments",
              collection_key="results",
              state_filter="modifiedDate"),
    Paginated("invoices",
              ["id", "companyId"],
              "/companies/{companyId}/data/invoices",
              collection_key="results",
              state_filter="modifiedDate",
              custom_formatter=trunc_payment_allocation_notes),
    Paginated("journal_entries",
              ["id", "companyId"],
              "/companies/{companyId}/data/journalEntries",
              collection_key="results",
              state_filter="modifiedDate"),
    Paginated("items",
              ["id", "companyId"],
              "/companies/{companyId}/data/items",
              collection_key="results",
              state_filter="modifiedDate"),
    Paginated("tax_rates",
              ["id", "companyId"],
              "/companies/{companyId}/data/taxRates",
              collection_key="results",
              state_filter="modifiedDate"),
    Events("events",
          ["eventTimeUtc", "companyId"],
          "/companies/{companyId}/reports/events",
          collection_key="data"),
    Financials("balance_sheets",
               ["companyId"],
               "/companies/{companyId}/data/financials/balanceSheet",
               returns_collection=False,
               custom_formatter=flatten_balance_sheets),
    Financials("profit_and_loss",
               ["companyId"],
               "/companies/{companyId}/data/financials/profitAndLoss",
               returns_collection=False,
               custom_formatter=flatten_profit_and_loss),
]
all_stream_ids = [s.tap_stream_id for s in all_streams]
