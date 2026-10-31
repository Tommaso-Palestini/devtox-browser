// Anti-fingerprinting di Devtox (in stile "farbling" di Brave).
// Gira prima degli script della pagina. Le letture che servono a riconoscerti
// (pixel del canvas, nome della GPU, numero di core) restituiscono valori
// leggermente diversi per ogni sito e per ogni avvio del browser, ma stabili
// dentro lo stesso sito: le pagine funzionano, il tracciamento tra siti no.
(() => {
  "use strict";
  const disabledHosts = $off_hosts;
  if (disabledHosts.includes(location.hostname)) return;

  // Seme = hash FNV-1a di (seme di sessione + sito)
  let seed = 2166136261;
  for (const ch of "$seed" + location.hostname) {
    seed ^= ch.charCodeAt(0);
    seed = Math.imul(seed, 16777619) >>> 0;
  }
  // Un bit pseudo-casuale per posizione: stesso pixel, stessa variazione
  const noiseBit = (index) => {
    let x = (seed ^ Math.imul(index, 2654435761)) >>> 0;
    x ^= x >>> 15;
    x = Math.imul(x, 2246822519) >>> 0;
    x ^= x >>> 13;
    return x & 1;
  };
  // Cambia il bit meno significativo del rosso di un pixel ogni 97: invisibile all'occhio
  const addNoise = (data) => {
    for (let i = 0; i < data.length; i += 4 * 97) data[i] ^= noiseBit(i);
  };

  const getImageData = CanvasRenderingContext2D.prototype.getImageData;
  CanvasRenderingContext2D.prototype.getImageData = function (...args) {
    const image = getImageData.apply(this, args);
    addNoise(image.data);
    return image;
  };

  // toDataURL/toBlob lavorano su una copia: il canvas originale resta intatto
  const noisyCopy = (canvas) => {
    if (!canvas.width || !canvas.height) return canvas;
    const copy = document.createElement("canvas");
    copy.width = canvas.width;
    copy.height = canvas.height;
    const context = copy.getContext("2d");
    context.drawImage(canvas, 0, 0);
    const image = getImageData.call(context, 0, 0, copy.width, copy.height);
    addNoise(image.data);
    context.putImageData(image, 0, 0);
    return copy;
  };
  const toDataURL = HTMLCanvasElement.prototype.toDataURL;
  HTMLCanvasElement.prototype.toDataURL = function (...args) {
    return toDataURL.apply(noisyCopy(this), args);
  };
  const toBlob = HTMLCanvasElement.prototype.toBlob;
  HTMLCanvasElement.prototype.toBlob = function (...args) {
    return toBlob.apply(noisyCopy(this), args);
  };

  // WebGL: niente modello esatto della scheda video
  const masked = { 0x9245: "WebKit", 0x9246: "WebKit WebGL" }; // UNMASKED_VENDOR/RENDERER
  for (const api of [window.WebGLRenderingContext, window.WebGL2RenderingContext]) {
    if (!api) continue;
    const getParameter = api.prototype.getParameter;
    api.prototype.getParameter = function (name) {
      return name in masked ? masked[name] : getParameter.call(this, name);
    };
  }

  // Numero di core uguale per tutti
  Object.defineProperty(Navigator.prototype, "hardwareConcurrency", {
    get: () => 4,
    configurable: true,
  });
})();
