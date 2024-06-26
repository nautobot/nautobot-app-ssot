# Frequently Asked Questions

## _Is the application actually a Single Source of Truth?_

In reality the application intends to have behaviors as if it was a SSoT. The difference being, the application intends to aggregate data in the real world where it is not feasible to have the System of Record be in a single system.

## Why did my ServiceNow job fail with an `IncompleteJSONError`?

```
An exception occurred: `IncompleteJSONError: lexical error: invalid char in json text. <meta (right here) ------^
```

This exception probably means that your ServiceNow developer instance is currently hibernating and needs to be awoken.
