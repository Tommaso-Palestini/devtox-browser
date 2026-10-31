# Contributing

Thanks for wanting to help. Bug reports, translations and small focused pull
requests are the most useful contributions right now.

## Reporting bugs

Open an issue with:

- the output of `devtox --check`
- what you did, what you expected and what happened
- the relevant part of `~/.local/state/devtox/devtox.log`

Security problems go through [SECURITY.md](SECURITY.md), not public issues.

## Development setup

Install the system libraries listed in the README, then:

```sh
python3 -m venv --system-site-packages .venv
.venv/bin/python -m devtox --new-instance
```

Run the tests before sending a pull request:

```sh
.venv/bin/python -m unittest     # fast, no window
sh scripts/check.sh              # everything, including a real start-up inside Xvfb
```

There are no Python dependencies beyond the standard library and PyGObject.
Please keep it that way unless there is a very good reason.

## How the code is organised

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) maps the modules and the start-up
sequence; [docs/adr](docs/adr/) records why the main choices were made. Add an ADR
when you make a choice that a future contributor would otherwise have to guess.

## Code conventions

- Match the style of the surrounding code. Comments and docstrings are written in
  Italian (the project's original language); English comments in new code are fine.
- Every user-visible string goes through `_()` (Python) or `{{...}}` (files in
  `devtox/resources/`). The source text is Italian.
- Keep the browser light: no background work when a panel is hidden, no network
  access that the user did not ask for. See [PRIVACY.md](PRIVACY.md); a change
  that adds a network connection must update it.

## Translations

Translations live in `devtox/locale/<language>.po` (standard gettext format,
read directly at runtime, no compilation step).

```sh
python3 scripts/update_po.py           # refresh every .po after changing strings
python3 scripts/update_po.py --check   # list missing translations
```

To add a language, copy `en.po` to `<code>.po`, translate the `msgstr` lines and
add the language to `LANGUAGES` in `devtox/i18n.py`. Placeholders such as
`{name}`, `$host` and HTML tags must stay exactly as in the original; the test
suite checks this.

## License

By contributing you agree that your contribution is licensed under the
GPL-3.0-or-later, like the rest of the project.
