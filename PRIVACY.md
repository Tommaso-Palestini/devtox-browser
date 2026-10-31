# Privacy policy

_Last updated: 31 October 2026. Applies to Devtox 0.1.0 and later._

Devtox is a program that runs on your computer. Its authors do not run any
server for it, so there is nobody on our side who could receive your data.

## What Devtox does not do

- **No telemetry, analytics or crash reporting.** Nothing about how you use the
  browser is sent anywhere.
- **No update checks.** Devtox never contacts its authors or any update server.
  You get new versions by updating your copy yourself.
- **No accounts and no sync.**
- **No downloaded lists.** The tracker blocklist is a local file that you edit.

## Network connections

Devtox only opens these connections:

| Connection | When |
|---|---|
| The websites you open | when you open them (including links, pages restored from your session, and resources those pages load) |
| Your search engine (DuckDuckGo by default, you can change it in `devtox://setup`) | when you type something that is not an address in the address bar, the start page or the command palette |
| Ollama on `127.0.0.1:11434` (your own computer) | only when you open the AI panel or use an AI action |
| `localhost` ports listed in `dev_ports` | when the start page or the local servers popup checks which dev servers are running (connections to your own computer only) |
| The Docker or Podman socket on your computer (a Unix socket, never the network) | only while the Docker panel is open, or when you press one of its buttons. A remote `DOCKER_HOST` (`tcp://`, `ssh://`) is ignored on purpose |

Devtox also reads your own entries in `/proc` to list the servers you are running
(port, program, folder, uptime). Nothing leaves your computer. Stopping a server
sends it `SIGTERM`, the same signal as Ctrl+C, and only after you click a stop button.

The websites you visit and the search engine you choose have their own privacy
policies. Devtox tries to limit what they learn (see below), but it cannot
control what they do with the data you send them.

## Data stored on your computer

| Data | Where | How to delete it |
|---|---|---|
| Settings and per-site shields | `~/.config/devtox/config.json` | delete the file |
| Tracker blocklist | `~/.config/devtox/blocklist.txt` | delete the file |
| History and bookmarks | `~/.local/share/devtox/devtox.sqlite` | palette → "Clear history"; history older than 90 days is deleted on start (`history_days`) |
| Open tabs (session) | `~/.local/share/devtox/session.json` | turn off "Reopen tabs on start" |
| Cookies, local storage, site data | `~/.local/share/devtox/` | `Ctrl+Shift+Delete` per site; turn off "Stay signed in to sites" to keep nothing between runs |
| Web cache, compiled filters and privacy extension | `~/.cache/devtox/` | delete the folder |
| Log (errors and warnings, no browsing history) | `~/.local/state/devtox/devtox.log` | delete the file |
| Screenshots you take | your Pictures folder | delete the files |
| Downloads | your Downloads folder | delete the files |

To remove everything, delete the four `devtox` folders listed above.

**Private tabs** (`Ctrl+Shift+N`) use a separate, in-memory profile: no history,
no session entry, and their cookies and site data disappear when you close the
last private tab. An HTTP exception you accept in a private tab is kept in memory
only and is never written to `config.json`.

## Protections that limit what websites learn

These are on by default and can be changed in `devtox://setup` or per site from the
shield in the address bar:

- HTTPS-only connections (except localhost and private networks)
- third-party cookies blocked and WebKit's Intelligent Tracking Prevention on
- a local tracker blocklist and blocking of `<a ping>` beacons
- noise added to canvas and WebGL fingerprinting, a fixed CPU core count
- the `Sec-GPC: 1` header and `navigator.globalPrivacyControl`
- the `Referer` header trimmed to the site origin
- camera, microphone, location and notification requests always denied
- WebRTC turned off, so it cannot reveal your local IP address

The GPC header and the Referer trimming come from a small WebKit extension that
is compiled on first start; `devtox --check` tells you whether it is active.

None of these makes you anonymous. If you need anonymity, use Tor Browser.

## The local AI assistant

The AI panel talks only to Ollama on `127.0.0.1`. Page text or selected text is
sent to that local model only when you press one of the AI actions. Commands the
model suggests are never run without your explicit confirmation.

## Changes

Changes to this policy are recorded in this file's history in the repository.
