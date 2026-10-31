# 3. Internal pages rendered in Python

Status: accepted (0.1.0)

## Context

The start page, setup, about and source pages need live local data (servers,
history, settings) and must be able to change settings safely.

## Decision

Serve them from a custom `devtox://` scheme whose handler calls a Python function
and returns HTML built from templates in `devtox/resources/`. Values are
escaped before they reach the template. The scheme is registered as local and
secure, and settings change only with a random token created at start-up.

## Consequences

- No local web server and no JavaScript bridge to the UI process.
- Pages are rendered on the main thread, so a page function must be fast (the
  start page reads `/proc` and SQLite in a few milliseconds) and must not raise:
  the handler logs exceptions and finishes the request with an error.
- Templates are plain HTML and CSS, easy to restyle and to screenshot in tests.
