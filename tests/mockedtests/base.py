"""
Base test class for mock integration tests for tap-codat.

These tests run the real tap code against mocked API responses — no external
tap-tester dependency required.
"""
import copy
import json
import os
import unittest
from unittest.mock import MagicMock, patch

from singer import metadata

import tap_codat
from tap_codat.context import Context
from tap_codat import streams as streams_


class CodatBaseTest:
    """Shared helpers and metadata expectations for mock integration tests."""

    default_start_date = "2023-01-01T00:00:00Z"
    PRIMARY_KEYS = "primary_keys"

    default_config = {
        "api_key": "test_api_key_12345",
        "start_date": "2023-01-01T00:00:00Z",
        "uat_urls": "false",
    }

    MOCK_COMPANIES = [
        {
            "id": "comp-001",
            "name": "Mock Company Alpha",
            "platform": "QuickBooks",
            "lastSync": "2024-06-15T10:00:00.00Z",
            "redirect": "https://example.com",
            "status": "Active",
            "dataConnections": [
                {"id": "conn-001", "integrationId": "int-001"}
            ],
        },
    ]

    MOCK_ACCOUNTS = [
        {
            "id": "acct-001",
            "name": "Cash",
            "description": "Cash account",
            "nominalCode": "1000",
            "isBankAccount": False,
            "currency": "USD",
            "type": "Asset",
            "modifiedDate": "2024-01-15T10:00:00.00Z",
        },
        {
            "id": "acct-002",
            "name": "Revenue",
            "description": "Revenue account",
            "nominalCode": "4000",
            "isBankAccount": False,
            "currency": "USD",
            "type": "Income",
            "modifiedDate": "2024-03-20T14:30:00.00Z",
        },
    ]

    MOCK_INVOICES = [
        {
            "id": "inv-001",
            "issueDate": "2024-02-01T00:00:00.00Z",
            "dueDate": "2024-03-01T00:00:00.00Z",
            "currency": "USD",
            "amountDue": 1500.00,
            "totalAmount": 1500.00,
            "status": "Submitted",
            "modifiedDate": "2024-02-15T08:00:00.00Z",
        },
    ]

    MOCK_COMPANY_INFO = {
        "companyName": "Mock Company Alpha",
        "registrationNumber": "REG-001",
        "currency": "USD",
    }

    MOCK_CONNECTIONS = [
        {
            "id": "conn-001",
            "integrationId": "int-001",
            "sourceId": "src-001",
            "platformName": "QuickBooks",
            "linkUrl": "https://example.com/link",
            "status": "Linked",
        },
    ]

    MOCK_EVENTS = [
        {
            "eventTimeUtc": "2024-05-01T12:00:00.00Z",
            "type": "DatasetStatusHasChanged",
            "description": "Dataset status changed",
        },
    ]

    MOCK_BALANCE_SHEET = {
        "currency": "USD",
        "reports": [
            {
                "date": "2024-01-31T00:00:00.00Z",
                "assets": {"name": "Assets", "value": 50000, "items": []},
                "liabilities": {"name": "Liabilities", "value": 20000, "items": []},
                "equity": {"name": "Equity", "value": 30000, "items": []},
            }
        ],
    }

    MOCK_PROFIT_AND_LOSS = {
        "currency": "USD",
        "reports": [
            {
                "date": "2024-01-31T00:00:00.00Z",
                "income": {"name": "Income", "value": 10000, "items": []},
                "costOfSales": {"name": "Cost of Sales", "value": 3000, "items": []},
                "expenses": {"name": "Expenses", "value": 2000, "items": []},
                "otherIncome": {"name": "Other Income", "value": 500, "items": []},
                "otherExpenses": {"name": "Other Expenses", "value": 100, "items": []},
            }
        ],
    }

    MOCK_BILLS = [
        {
            "id": "bill-001",
            "reference": "BILL-001",
            "supplierRef": {"id": "sup-001", "supplierName": "Vendor A"},
            "issueDate": "2024-01-10T00:00:00.00Z",
            "dueDate": "2024-02-10T00:00:00.00Z",
            "currency": "USD",
            "status": "Open",
            "totalAmount": 500.00,
            "amountDue": 500.00,
            "modifiedDate": "2024-01-15T09:00:00.00Z",
        },
    ]

    ALL_STREAM_IDS = {
        "companies", "accounts", "bank_accounts", "bank_account_transactions",
        "bank_statements", "bank_statement_lines", "bills", "company_info",
        "credit_notes", "customers", "payments", "suppliers", "connections",
        "bill_payments", "invoices", "journal_entries", "items", "tax_rates",
        "events", "balance_sheets", "profit_and_loss",
    }

    SYNCABLE_STREAM_IDS = {s.tap_stream_id for s in streams_.all_streams}

    @classmethod
    def expected_metadata(cls):
        return {
            "companies": {cls.PRIMARY_KEYS: {"id"}},
            "accounts": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "bank_accounts": {cls.PRIMARY_KEYS: {"accountName", "companyId", "connectionId"}},
            "bank_account_transactions": {cls.PRIMARY_KEYS: {"companyId", "bankAccountId", "_transactionIndex"}},
            "bank_statements": {cls.PRIMARY_KEYS: {"accountName", "companyId"}},
            "bank_statement_lines": {cls.PRIMARY_KEYS: {"companyId", "accountName", "_lineIndex"}},
            "bills": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "company_info": {cls.PRIMARY_KEYS: {"companyId"}},
            "credit_notes": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "customers": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "payments": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "suppliers": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "connections": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "bill_payments": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "invoices": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "journal_entries": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "items": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "tax_rates": {cls.PRIMARY_KEYS: {"id", "companyId"}},
            "events": {cls.PRIMARY_KEYS: {"eventTimeUtc", "companyId"}},
            "balance_sheets": {cls.PRIMARY_KEYS: {"companyId"}},
            "profit_and_loss": {cls.PRIMARY_KEYS: {"companyId"}},
        }

    @classmethod
    def _create_context(cls, config=None, state=None):
        """Create a Context with mocked Client.GET."""
        cfg = config or dict(cls.default_config)
        st = state or {}
        ctx = Context(cfg, st)
        ctx.client.GET = MagicMock(side_effect=cls._mock_client_GET())
        return ctx

    @classmethod
    def _mock_client_GET(cls):
        """Create a mock side_effect for Client.GET.

        Returns deep copies so that custom_formatters (e.g.
        flatten_balance_sheets) that mutate in-place don't corrupt the
        class-level mock data between tests.
        """

        def mock_fn(request_kwargs, tap_stream_id):
            path = request_kwargs.get("path", "")

            if path == "/companies":
                return copy.deepcopy({"results": cls.MOCK_COMPANIES})
            elif "/data/accounts" in path:
                return copy.deepcopy({"results": cls.MOCK_ACCOUNTS})
            elif "/data/invoices" in path:
                return copy.deepcopy({"results": cls.MOCK_INVOICES})
            elif "/data/info" in path:
                return copy.deepcopy(cls.MOCK_COMPANY_INFO)
            elif "/reports/events" in path:
                return copy.deepcopy({"data": cls.MOCK_EVENTS})
            elif "/financials/balanceSheet" in path:
                return copy.deepcopy(cls.MOCK_BALANCE_SHEET)
            elif "/financials/profitAndLoss" in path:
                return copy.deepcopy(cls.MOCK_PROFIT_AND_LOSS)
            elif "/data/bills" in path and "billpayments" not in path:
                return copy.deepcopy({"results": cls.MOCK_BILLS})
            elif "/data/bankAccounts" in path:
                return {"results": []}
            elif "/data/bankStatements" in path:
                return []
            elif "/data/creditNotes" in path:
                return {"results": []}
            elif "/data/customers" in path:
                return {"results": []}
            elif "/data/payments" in path:
                return {"results": []}
            elif "/data/suppliers" in path:
                return {"results": []}
            elif "/data/billpayments" in path:
                return {"results": []}
            elif "/data/journalEntries" in path:
                return {"results": []}
            elif "/data/items" in path:
                return {"results": []}
            elif "/data/taxRates" in path:
                return {"results": []}
            elif "/connections" in path and "/data/" not in path:
                return copy.deepcopy(cls.MOCK_CONNECTIONS)
            else:
                return {"results": []}

        return mock_fn

    @classmethod
    def _run_discover(cls):
        """Run discover() and return the catalog."""
        ctx = cls._create_context()
        return tap_codat.discover(ctx)

    @classmethod
    def _make_selected_catalog(cls, stream_names=None):
        """Build a catalog with selected=True for the given streams.
        If stream_names is None, select all streams."""
        catalog = cls._run_discover()
        for entry in catalog.streams:
            is_selected = stream_names is None or entry.tap_stream_id in stream_names
            mdata = metadata.to_map(entry.metadata)
            mdata = metadata.write(mdata, (), 'selected', is_selected)
            entry.metadata = metadata.to_list(mdata)
        return catalog
