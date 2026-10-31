// Password di Devtox: gira in un mondo JavaScript isolato ("devtox-passwords").
// La pagina non vede questo codice e non può usare il suo canale verso il browser:
// window.webkit.messageHandlers.devtoxPasswords esiste solo in questo mondo.
// Non compila mai da solo: lo fa solo quando il browser lo chiede dopo un tuo clic.
(() => {
  "use strict";
  const channel = window.webkit && window.webkit.messageHandlers && window.webkit.messageHandlers.devtoxPasswords;
  if (!channel || window.__devtoxFill) return;
  const send = (message) => channel.postMessage(JSON.stringify(message));

  const visible = (input) => {
    const box = input.getBoundingClientRect();
    return box.width > 0 && box.height > 0 && getComputedStyle(input).visibility !== "hidden";
  };
  const passwordFields = () => [...document.querySelectorAll("input[type=password]")].filter(visible);

  // Il campo utente: quello dichiarato come tale, altrimenti l'ultimo campo di testo prima della password
  const usernameFor = (password) => {
    const scope = password.form || document;
    const declared = scope.querySelector('input[autocomplete~="username"], input[autocomplete~="email"]');
    if (declared && visible(declared)) return declared;
    const fields = [...scope.querySelectorAll("input")].filter(visible);
    const before = fields.slice(0, fields.indexOf(password)).reverse();
    return before.find((f) => ["text", "email", "tel", ""].includes((f.getAttribute("type") || "").toLowerCase())) || null;
  };

  // Un modulo di accesso compare (anche dopo, nelle app a pagina singola): lo si dice una volta
  let announced = false;
  const announce = () => {
    if (announced || !passwordFields().length) return;
    announced = true;
    send({ type: "form", origin: location.origin });
  };
  let pending = 0;
  const observer = new MutationObserver(() => {
    if (announced) { observer.disconnect(); return; }
    clearTimeout(pending);
    pending = setTimeout(announce, 300);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
  announce();

  // Invio del modulo (submit, Invio nella password o clic sul pulsante): si propone di salvare
  let lastSent = "";
  const capture = (password) => {
    if (!password || !password.value) return;
    const user = usernameFor(password);
    const key = (user ? user.value : "") + "\u0000" + password.value;
    if (key === lastSent) return;
    lastSent = key;
    send({ type: "submit", origin: location.origin, username: user ? user.value : "", password: password.value });
  };
  document.addEventListener("submit", (event) => {
    capture(event.target.querySelector && event.target.querySelector("input[type=password]"));
  }, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.type === "password") capture(event.target);
  }, true);
  document.addEventListener("click", (event) => {
    const button = event.target.closest && event.target.closest('button, input[type=submit], [role=button]');
    if (!button) return;
    const scope = button.form || button.closest("form") || document;
    const password = [...scope.querySelectorAll("input[type=password]")].find((p) => p.value);
    if (password) capture(password);
  }, true);

  // Compila con il valore scelto, solo se l'origine è ancora quella attesa
  const setValue = (input, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value").set;
    setter.call(input, value);  // anche nei campi gestiti da React & co.
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  };
  window.__devtoxFill = (origin, username, password) => {
    if (location.origin !== origin) return false;
    const field = passwordFields()[0];
    if (!field) return false;
    const user = usernameFor(field);
    if (user && username) setValue(user, username);
    setValue(field, password);
    lastSent = (username || "") + "\u0000" + password;  // già salvata: niente proposta all'invio
    field.focus();
    return true;
  };
})();
