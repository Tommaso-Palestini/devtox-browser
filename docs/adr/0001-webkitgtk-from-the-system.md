# 1. WebKitGTK from the system, not a bundled engine

Status: accepted (0.1.0)

## Context

A browser engine is the largest and most security-critical part of a browser.
Bundling Chromium (Electron, CEF) or Gecko means shipping hundreds of megabytes
and taking on the duty of releasing every engine security fix ourselves.

## Decision

Use WebKitGTK 4.1, GTK 3 and VTE from the distribution, through PyGObject.
Devtox ships only Python, a few resources and a small C web extension.

## Consequences

- Engine security fixes arrive with normal system updates; the README says so.
- The install is a few hundred kilobytes and needs no build step besides the
  optional web extension.
- Some heavy web apps (video calls in particular) work better in Chromium. This is
  listed under "Known limitations".
- System libraries cannot come from pip: `deps.py` checks them at start-up and
  prints the packages to install for Debian, Fedora and Arch.
