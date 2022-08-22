# Changelog

## 0.5.2
 * Fix `collection_key` on paginated endpoints due to API response key being renamed to `results` [#18](https://github.com/singer-io/tap-codat/pull/18)

## 0.5.1
  * Fix KeyError on `companies` stream due to API response key being renamed to `results` [#14](https://github.com/singer-io/tap-codat/pull/14)

## 0.5.0
**Functional changes:**
- Retry requests which fail with a 500, 501, or 502 error code
- Added fields to the Accounts stream:
  - description
  - fullyQualifiedCategory
  - modifiedDate
  - sourceModifiedDate
- Added `companyId` field to Payment Allocations Stream
- Migrated Bank Statement Lines from a subfield of Bank Statements to its own stream
  - Bank Statements can have arbitrarily long line items lists which exceeded Stitch's 4mb API integration limit. Each line item is now its own row in the Bank Statement Lines table.

**New streams**
- Added Bills stream
- Added Bill Payments stream
- Added Connections stream
- Added Events stream
- Added Items stream
- Added Journal Entries stream
- Added Tax Rates stream
- Added Bank Accounts stream
- Added Bank Account Transactions stream

**Incrementalized streams:**
- Accounts
- Bank Statements
- Bills
- Credit Notes
- Customers
- Payments
- Suppliers
- Connections
- Bill Payments
- Invoices
- Journal Entries
- Items
- Tax Rates

## 0.4.0
  * Update stream selection to use metadata instead of schema annotations [#7](https://github.com/singer-io/tap-codat/pull/7)

## 0.3.1
  * Update version of `requests` to `2.20.0` in response to CVE 2018-18074

## 0.3.0
  * Adds companyId as a primary key to all streams [#4](https://github.com/singer-io/tap-codat/pull/4)
  * Updates balance and availableBalance to be converted to numbers before using a string []()


## 0.2.1
  * Fixes an inconsistency in the C library strftime where dates < 1000 would be formatted strangely [#3](https://github.com/singer-io/tap-codat/pull/3)

## 0.1.2
  * Adds id field to bank_statements schema
