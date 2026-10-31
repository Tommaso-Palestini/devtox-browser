# 4. Dev servers discovered from /proc

Status: accepted (0.1.0)

## Context

The first version probed a fixed list of ports (`dev_ports`). It missed servers
on other ports and could not say what a port was: a Vite project, Django, or
Ollama.

## Decision

`servers.py` reads `/proc/net/tcp{,6}` for sockets in LISTEN state owned by the
user, finds the process that holds each socket through `/proc/<pid>/fd`, and
reports the tool (from the command line), the working directory (the project)
and the uptime. `dev_ports` remains for servers that `/proc` cannot attribute to
the user, such as Docker or root services; those are probed with a connect.

## Consequences

- Works with no configuration and shows the project folder, which is what a
  developer recognises at a glance.
- Linux only, like the rest of the browser. Reads only the user's own `/proc`
  entries: no privileges and no network.
- The same data feeds the start page, the rail popover and `sr servers`.
