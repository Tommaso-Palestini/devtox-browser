# 2. A local, hand-edited blocklist

Status: accepted (0.1.0)

## Context

Filter lists such as EasyList are large, change daily and must be downloaded.
Downloading them means a network connection the user did not ask for and a
dependency on a third party, which conflicts with the promise in PRIVACY.md.

## Decision

Block trackers with a short plain-text list of domains in
`~/.config/shellrunner/blocklist.txt`, compiled into a WebKit content filter.
Nothing is downloaded. The user edits the file and reloads it from the menu.

## Consequences

- No background network traffic and no list maintainer to trust.
- Blocking is much narrower than uBlock Origin; the README says so plainly.
- The same filter carries the HTTPS-only rules, so their order matters:
  HTTPS rules and their exceptions come before the blocks (`build_rules`).
