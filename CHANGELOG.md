# Changelog

## 0.1.0 (non ancora pubblicata)

Prima versione pubblica.

### Da Shellrunner a Devtox

Durante lo sviluppo il browser si chiamava Shellrunner. Ora tutto si chiama Devtox:
il programma `devtox`, il comando `dx` (prima `sr`), le pagine `devtox://` (prima `sr://`),
il pacchetto `devtox-browser` e l'ID `io.github.Tommaso_Palestini.devtox-browser`.
Chi aveva già un profilo non perde niente: al primo avvio le cartelle `shellrunner`
in `~/.config`, `~/.local/share`, `~/.cache` e `~/.local/state` diventano `devtox`,
e le tab salvate passano a `devtox://`. `install.sh` toglie i file della vecchia
installazione e, se Shellrunner era il browser predefinito, lo sostituisce con Devtox.

- Browser WebKitGTK con terminale VTE integrato, command palette, comando `dx`.
- Pagina iniziale con i server in esecuzione sul PC letti da `/proc` (porta, strumento,
  cartella del progetto, uptime), pagine recenti, preferiti e barra dei tasti.
- Ferma i server di sviluppo uno per uno o tutti insieme (pagina iniziale, popup del rail,
  `dx stop`), con SIGTERM come Ctrl+C. Le app desktop in ascolto (Steam, Syncthing,
  l'editor...) non compaiono e non vengono mai fermate.
- Pannello Docker (`Ctrl+Shift+D`): container per progetto, avvio, arresto, riavvio, log nel
  terminale, porte pubblicate. Solo il socket locale di Docker o Podman, solo a pannello aperto.
- Import da altri browser (`devtox://import`): preferiti e cronologia recente da Firefox,
  Zen, LibreWolf e dai browser Chromium (Chrome, Brave, Edge, Vivaldi, Opera, Opera GX),
  anche Flatpak e Snap. Niente password né cookie; Tor Browser mai.
- Sandbox dei processi delle pagine (bubblewrap) attiva: prima era spenta.
- Gestore password nel portachiavi del sistema (libsecret): proposta di salvataggio,
  compilazione con un clic solo sull'origine esatta e solo in HTTPS o su localhost, script
  in un mondo JavaScript isolato, import dal CSV di Firefox, Chrome, Opera, Brave, Edge e
  Bitwarden (`devtox://passwords`).
- Protezione anti-phishing attiva di base: lista pubblica Phishing.Database (MIT) controllata
  sul PC, completa una volta a settimana e domini nuovi ogni giorno; le piattaforme condivise
  (vercel.app, github.io, sites.google.com...) non si bloccano mai per intero.
- Strumenti attivabili in `devtox://setup`: pannello Docker, avviso quando parte un server
  (spento di base), assistente IA.
- Configurazione a righe (spiegazione e controlli) con anteprima del motore di ricerca
  e riepilogo della privacy che si aggiorna mentre scegli.
- Interfaccia in inglese e in italiano (file `.po`, scelta automatica dalla lingua del sistema).
- Configurazione al primo avvio (`devtox://setup`): lingua, motore di ricerca, livello di privacy,
  porte di sviluppo, assistente IA, browser predefinito. Riavvio dalla pagina quando serve.
- Motori di ricerca: DuckDuckGo, Startpage, Brave Search, Mojeek, Ecosia, Google.
- Privacy: HTTPS-only, blocklist locale, anti-fingerprinting, GPC, Referer ridotto,
  cookie di terze parti bloccati, tab private, scudi per sito, nessuna telemetria.
- Strumenti: server locali, rete, memoria, download, responsive, screenshot,
  sorgente, visualizzatore JSON, IA locale con Ollama.
- Installazione con `install.sh` (senza sudo) o `pip`, file `.desktop`, metadati AppStream, icona.
- Controllo delle librerie di sistema all'avvio con i pacchetti da installare.
- Estensione privacy compilata da sola al primo avvio nella cache del profilo.
- Log su file, `devtox://about` con licenza e informativa privacy, `devtox --check`.
- Gli indirizzi passati a `devtox` vanno alla finestra già aperta.
- Documenti: PRIVACY.md, SECURITY.md, CONTRIBUTING.md.

### Correzioni prima del rilascio

- Senza il socket di `dx` (percorso troppo lungo, permessi) la finestra non si apriva.
- Le eccezioni HTTP accettate in una tab privata finivano in `config.json`.
- L'interruttore anti-fingerprinting per sito non faceva nulla con la protezione spenta in generale.
- Il popup dei server locali restava su "Cerco…" se `dev_ports` era vuoto.
- La finestra dei dati del sito poteva aggiornarsi dopo essere stata chiusa.
- Lo stato "non riuscito" dei download dipendeva dal testo mostrato (rotto con le traduzioni).
- Connessione a Ollama non chiusa in caso di errore nell'elenco dei modelli.
- Il comando `dx` non era raggiungibile dai terminali integrati dopo `install.sh`.
