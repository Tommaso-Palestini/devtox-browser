// Visualizzatore JSON di Shellrunner. Gira in un mondo JavaScript isolato,
// solo sui documenti JSON aperti direttamente. Costruisce l'albero con
// textContent (mai innerHTML): il contenuto resta sempre testo.
(() => {
  "use strict";
  const type = document.contentType || "";
  if (!/^application\/([\w.-]+\+)?json$/.test(type) && type !== "text/json") return;
  const body = document.body;
  if (!body) return;
  const raw = body.textContent;
  if (!raw || raw.length > 5 * 1024 * 1024) return; // oltre 5 MB resta testo semplice

  let data;
  try {
    data = JSON.parse(raw);
  } catch (error) {
    return; // non è JSON valido: lo lasciamo com'è
  }

  const make = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  };

  let nodeCount = 0;
  const render = (value, key, depth) => {
    nodeCount += 1;
    const isArray = Array.isArray(value);
    const label = make("span", "key", key === null ? "" : key + ": ");

    if (value !== null && typeof value === "object") {
      const entries = isArray ? value.map((v, i) => [i, v]) : Object.entries(value);
      const details = make("details");
      details.open = depth < 2 || nodeCount < 300;
      const summary = make("summary");
      summary.append(label, make("span", "meta", isArray ? `[${entries.length}]` : `{${entries.length}}`));
      details.append(summary);
      const list = make("div", "children");
      for (const [childKey, child] of entries) list.append(render(child, String(childKey), depth + 1));
      details.append(list);
      return details;
    }
    const row = make("div", "leaf");
    const kind = value === null ? "null" : typeof value;
    const text = kind === "string" ? JSON.stringify(value) : String(value);
    row.append(label, make("span", kind, text));
    return row;
  };

  const style = make("style");
  style.textContent = `
    :root { color-scheme: dark; }
    body { margin: 0; background: #0e0e10; color: #ececee;
           font: 13px/1.6 "Fira Mono", ui-monospace, monospace; }
    .sr-bar { position: sticky; top: 0; display: flex; gap: 8px; padding: 8px 16px;
              background: #161618; border-bottom: 1px solid #26262a;
              font-family: "Fira Sans", system-ui, sans-serif; }
    .sr-bar button { background: transparent; color: #94969d; border: 1px solid #3a3a3f;
                     border-radius: 999px; padding: 3px 14px; font: inherit; cursor: pointer; }
    .sr-bar button:hover { color: #ececee; border-color: #94969d; }
    .sr-bar button[aria-pressed="true"] { color: #ececee; border-color: #73c991; }
    .sr-tree { padding: 12px 16px; }
    .sr-tree details > .children, .sr-tree .leaf { padding-left: 18px; }
    .sr-tree details > .children { border-left: 1px solid #26262a; margin-left: 4px; }
    .sr-tree summary { cursor: pointer; }
    .sr-tree summary::marker { color: #6b6d73; }
    .key { color: #ececee; } .meta { color: #94969d; }
    .string { color: #73c991; } .number { color: #6aa1e0; }
    .boolean { color: #6aa1e0; } .null { color: #94969d; }
    .sr-raw { padding: 12px 16px; white-space: pre-wrap; word-break: break-all; margin: 0; }
  `;

  const tree = make("div", "sr-tree");
  tree.append(render(data, null, 0));
  const rawView = make("pre", "sr-raw", JSON.stringify(data, null, 2));
  rawView.hidden = true;

  const bar = make("div", "sr-bar");
  const treeButton = make("button", "", "{{Albero}}");
  const rawButton = make("button", "", "{{Testo formattato}}");
  const expandButton = make("button", "", "{{Espandi tutto}}");
  const collapseButton = make("button", "", "{{Comprimi tutto}}");
  const show = (showTree) => {
    tree.hidden = !showTree;
    rawView.hidden = showTree;
    treeButton.setAttribute("aria-pressed", String(showTree));
    rawButton.setAttribute("aria-pressed", String(!showTree));
  };
  treeButton.onclick = () => show(true);
  rawButton.onclick = () => show(false);
  expandButton.onclick = () => tree.querySelectorAll("details").forEach((d) => (d.open = true));
  collapseButton.onclick = () => tree.querySelectorAll("details").forEach((d, i) => (d.open = i === 0));
  bar.append(treeButton, rawButton, expandButton, collapseButton);
  show(true);

  (document.head || document.documentElement).append(style);
  body.replaceChildren(bar, tree, rawView);
})();
