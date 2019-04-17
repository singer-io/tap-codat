# tap-codat

This is a [Singer](https://singer.io) tap that produces JSON-formatted data
following the [Singer
spec](https://github.com/singer-io/getting-started/blob/master/docs/SPEC.md).

This tap:

- Pulls raw data from [Codat](https://www.codat.io/)
- Extracts the following resources:
  - [Accounts](https://docs.codat.io/reference/accounts)
  - [Companies](https://docs.codat.io/reference/companies)
  - [Balance Sheets](https://docs.codat.io/reference/financials#financials_balancesheet)
  - [Bank Statements](https://docs.codat.io/reference/bankstatements)
  - [Bills](https://docs.codat.io/reference/bills)
  - [Company Info](https://docs.codat.io/reference/info)
  - [Credit Notes](https://docs.codat.io/reference/creditnotes)
  - [Customers](https://docs.codat.io/reference/customers)
  - [Invoices](https://docs.codat.io/reference/invoices)
  - [Payments](https://docs.codat.io/reference/payments)
  - [Profit and Loss](https://docs.codat.io/reference/financials#financials_profitandloss)
  - [Suppliers](https://docs.codat.io/reference/suppliers)
- Outputs the schema for each resource

## Quick Start

1. Install

    pip install tap-codat

2. Get an API key

   Refer to the Codat documentation
   [here](https://docs.codat.io/docs/your-first-call-to-the-api-using-api-explorer).

3. Create the config file

   You must create a JSON configuration file that looks like this:

   ```json
   {
     "start_date": "2010-01-01",
     "api_key": "your-api-key",
     "uat_urls": "true"
   }
   ```

   The `start_date` is the date at which the tap will begin pulling data for
   streams that support this feature. Note that in the initial version of this
   tap, this date is unused, as all streams replicate all of the data from
   Codat during every run.

   Replace `your-api-key` with the API key you received from Codat. If this
   token is for the UAT environment, change `uat_urls` to `true`.

4. Run the Tap in Discovery Mode

    tap-codat -c config.json -d

   See the Singer docs on discovery mode
   [here](https://github.com/singer-io/getting-started/blob/master/docs/DISCOVERY_MODE.md).

5. Run the Tap in Sync Mode

    tap-codat -c config.json -p catalog-file.json

## Data Formatting

For a few endpoints, this tap reformats the structure of "reports" received
from Codat. An example is the `balance_sheets` stream, which returns a
structure like this:

```json
"reports": [
    {
        "assets": {
            "name": "Top-level Category",
            "value": 1,
            "items": [
                {"name": "Inner category A", "value": 2},
                {"name": "Inner category B", "value": 3}
            ]
        }
    }
]
```

Here, `assets` describes a hierarchical structure. It is recursive in that any
of the `items` can themselves contain an array of items. This is not a
structure that easily can fit into a flat, tabular structure. To alleviate
this, this tap restructures this data into this format:


```json
"reports": [
    {
        "assets": [
            {
                "name": "Top-level Category",
                "value": 1,
                "name_0": "Top-level Category"
            },
            {
                "name": "Inner category A",
                "value": 2,
                "name_0": "Top-level Category",
                "name_1": "Inner category A"
            },
            {
                "name": "Inner category B",
                "value": 3,
                "name_0": "Top-level Category",
                "name_1": "Inner category B"
            },
        ]
    }
]
```

The structure is flattened into a single array of objects. The `"name"` and
`"value"` properties are left as-is for each item, but now each items contains
properties `"name_X"` where X represents the category hierarchy. That is, if
your category hierarchy is

```
A
- B
- - C
- D
E
- F
```

Then `name_0` will always be either `A` or `E`, `name_1` will always be `B`,
`D`, or `F` and `name_2` will only ever be `C`.

---

Copyright &copy; 2017 Stitch
