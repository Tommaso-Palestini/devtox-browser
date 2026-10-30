# Security policy

## Supported versions

Shellrunner is young: only the latest release gets security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Use GitHub's private vulnerability reporting: on the repository page, open the
**Security** tab and choose **Report a vulnerability**. Include the output of
`shellrunner --check`, the steps to reproduce and what an attacker could achieve.

You should get a first answer within a week. Once a fix is released, the report
is credited in the changelog unless you prefer to stay anonymous.

## Scope

In scope: the Shellrunner code in this repository, for example

- a web page reaching `sr://` pages, the terminal, the `sr` socket or local files
- a way around HTTPS-only, the blocklist, private tabs or the download protections
- the AI panel running a command without confirmation
- the privacy extension (`shellrunner/webext/`)

Out of scope, please report upstream instead:

- bugs in the web engine itself: [WebKitGTK](https://webkitgtk.org/) (and your
  distribution, which ships it)
- bugs in GTK, VTE, GLib or PyGObject
- websites that still manage to fingerprint the browser by other means: this is
  a known limit, but ideas to improve it are welcome as normal issues

## Hardening notes

- Web content runs in WebKitGTK's sandboxed web processes; Shellrunner adds no
  JavaScript bridge from web pages to the browser, the terminal or the shell.
- `sr://` pages are registered as local: ordinary web pages cannot load or link
  to them. Settings changes from `sr://setup` also need a per-process random token.
- The `sr` control socket lives in `$XDG_RUNTIME_DIR` with mode `0600` and checks
  the peer's user id.
- Downloads are never opened automatically, never overwrite files, and need
  confirmation for executable file types.
