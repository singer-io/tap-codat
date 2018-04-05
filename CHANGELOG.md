# Changelog

## 0.3.0
  * Adds companyId as a primary key to all streams [#4](https://github.com/singer-io/tap-codat/pull/4)
  * Updates balance and availableBalance to be converted to numbers before using a string []()


## 0.2.1
  * Fixes an inconsistency in the C library strftime where dates < 1000 would be formatted strangely [#3](https://github.com/singer-io/tap-codat/pull/3)

## 0.1.2
  * Adds id field to bank_statements schema
