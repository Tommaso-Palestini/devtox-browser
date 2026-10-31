#!/usr/bin/env python3
"""Raccoglie i testi da tradurre e aggiorna devtox/locale/<lingua>.po.

  python3 scripts/update_po.py           aggiorna tutti i .po esistenti
  python3 scripts/update_po.py --check   esce con errore se mancano traduzioni

Testi: le chiamate _("...") nel codice Python e i {{...}} nelle risorse.
Le traduzioni già presenti restano; quelle non più usate finiscono in fondo
come commenti "#~", come fa gettext.
"""

import ast
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "devtox")
LOCALE_DIR = os.path.join(PACKAGE, "locale")
TRANSLATABLE_RE = re.compile(r"\{\{(.+?)\}\}", re.DOTALL)
PLACEHOLDER_RE = re.compile(r"\{[a-z_]*(?::[^}]*)?\}|\$[a-z_]+|<[^>]+>")

sys.path.insert(0, PACKAGE)
from i18n import parse_po  # noqa: E402  (i18n non dipende da GLib)


def python_strings(path):
    with open(path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), path)
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("_", "N_")
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            yield node.args[0].value, node.lineno


def resource_strings(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    for match in TRANSLATABLE_RE.finditer(text):
        yield " ".join(match.group(1).split()), text.count("\n", 0, match.start()) + 1


def collect():
    """{msgid: [riferimenti]} nell'ordine in cui compaiono."""
    found = {}
    sources = sorted(glob.glob(os.path.join(PACKAGE, "**", "*.py"), recursive=True))
    for path in sources:
        for text, line in python_strings(path):
            found.setdefault(text, []).append(f"{os.path.relpath(path, ROOT)}:{line}")
    for path in sorted(glob.glob(os.path.join(PACKAGE, "resources", "*"))):
        if path.endswith((".html", ".js")):
            for text, line in resource_strings(path):
                found.setdefault(text, []).append(f"{os.path.relpath(path, ROOT)}:{line}")
    return found


def quote(text):
    escaped = text.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
    lines = escaped.split("\n")
    if len(lines) == 1 and len(escaped) < 70:
        return f'"{escaped}"'
    parts = [line + "\\n" for line in lines[:-1]] + ([lines[-1]] if lines[-1] else [])
    return '""\n' + "\n".join(f'"{part}"' for part in parts)


def write_po(path, language, found, existing):
    out = [
        f"# Traduzione di Devtox: {language}.",
        "# Il testo sorgente (msgid) è in italiano. Aggiorna con: python3 scripts/update_po.py",
        'msgid ""',
        'msgstr ""',
        '"Content-Type: text/plain; charset=UTF-8\\n"',
        f'"Language: {language}\\n"',
        "",
    ]
    for msgid, refs in found.items():
        out.append("#: " + " ".join(refs[:4]))
        out.append("msgid " + quote(msgid))
        out.append("msgstr " + quote(existing.get(msgid, "")))
        out.append("")
    for msgid, msgstr in existing.items():
        if msgid not in found:
            out.append("#~ msgid " + quote(msgid).replace("\n", "\n#~ "))
            out.append("#~ msgstr " + quote(msgstr).replace("\n", "\n#~ "))
            out.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))


def problems(found, catalog):
    """Testi senza traduzione o con segnaposto diversi dall'originale."""
    result = []
    for msgid in found:
        msgstr = catalog.get(msgid)
        if not msgstr:
            result.append(f"manca: {msgid!r}")
        elif sorted(PLACEHOLDER_RE.findall(msgid)) != sorted(PLACEHOLDER_RE.findall(msgstr)):
            result.append(f"segnaposto diversi: {msgid!r} -> {msgstr!r}")
    return result


def main():
    found = collect()
    status = 0
    for path in sorted(glob.glob(os.path.join(LOCALE_DIR, "*.po"))):
        language = os.path.splitext(os.path.basename(path))[0]
        catalog = parse_po(path)
        if "--check" in sys.argv:
            issues = problems(found, catalog)
            for issue in issues:
                print(f"{language}: {issue}")
            status = status or bool(issues)
        else:
            write_po(path, language, found, catalog)
            missing = sum(1 for msgid in found if not catalog.get(msgid))
            print(f"{language}: {len(found)} testi, {missing} da tradurre")
    return status


if __name__ == "__main__":
    sys.exit(main())
