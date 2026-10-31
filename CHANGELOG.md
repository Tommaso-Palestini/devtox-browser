# Changelog

## 0.1.0 (non ancora pubblicata)

Prima versione pubblica.

- Browser WebKitGTK con terminale VTE integrato, command palette, comando `sr`.
- Pagina iniziale con i server in esecuzione sul PC letti da `/proc` (porta, strumento,
  cartella del progetto, uptime), pagine recenti, preferiti e barra dei tasti.
- Configurazione a righe (spiegazione e controlli) con anteprima del motore di ricerca
  e riepilogo della privacy che si aggiorna mentre scegli.
- Interfaccia in inglese e in italiano (file `.po`, scelta automatica dalla lingua del sistema).
- Configurazione al primo avvio (`sr://setup`): lingua, motore di ricerca, livello di privacy,
  porte di sviluppo, assistente IA, browser predefinito. Riavvio dalla pagina quando serve.
- Motori di ricerca: DuckDuckGo, Startpage, Brave Search, Mojeek, Ecosia, Google.
- Privacy: HTTPS-only, blocklist locale, anti-fingerprinting, GPC, Referer ridotto,
  cookie di terze parti bloccati, tab private, scudi per sito, nessuna telemetria.
- Strumenti: server locali, rete, memoria, download, responsive, screenshot,
  sorgente, visualizzatore JSON, IA locale con Ollama.
- Installazione con `install.sh` (senza sudo) o `pip`, file `.desktop`, metadati AppStream, icona.
- Controllo delle librerie di sistema all'avvio con i pacchetti da installare.
- Estensione privacy compilata da sola al primo avvio nella cache del profilo.
- Log su file, `sr://about` con licenza e informativa privacy, `shellrunner --check`.
- Gli indirizzi passati a `shellrunner` vanno alla finestra già aperta.
- Documenti: PRIVACY.md, SECURITY.md, CONTRIBUTING.md.

### Correzioni prima del rilascio

- Senza il socket di `sr` (percorso troppo lungo, permessi) la finestra non si apriva.
- Le eccezioni HTTP accettate in una tab privata finivano in `config.json`.
- L'interruttore anti-fingerprinting per sito non faceva nulla con la protezione spenta in generale.
- Il popup dei server locali restava su "Cerco…" se `dev_ports` era vuoto.
- La finestra dei dati del sito poteva aggiornarsi dopo essere stata chiusa.
- Lo stato "non riuscito" dei download dipendeva dal testo mostrato (rotto con le traduzioni).
- Connessione a Ollama non chiusa in caso di errore nell'elenco dei modelli.
- Il comando `sr` non era raggiungibile dai terminali integrati dopo `install.sh`.
