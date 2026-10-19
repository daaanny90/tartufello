# fiuto, app

PWA in Vue 3 + TypeScript + Vite. Gira tutta sul telefono: niente server, niente account.

## Comandi

```sh
npm install
npm run dev        # sviluppo
npm test           # unit test (Vitest)
npm run build      # typecheck + build di produzione in dist/
npm run e2e        # smoke test sul build, con Chromium locale e GPS simulato
```

`npm run e2e` vuole il build già fatto e Chromium in `/opt/pw-browsers/chromium` (o `CHROMIUM_PATH`). Usa la fixture sintetica `e2e/fixtures/synthetic-vth.pmtiles` se c'è; le schermate finiscono in `e2e/screenshots/` (o `SCREENSHOTS`).

Per installarla sul telefono serve HTTPS (il service worker e il GPS lo richiedono): hosting statico qualsiasi o il server di casa dietro un certificato.

## Struttura

| Cartella | Cosa fa |
|---|---|
| `src/rules/` | Calendario ER 2026-2030 come dati (`er-calendar-2026-2030.json`) e calcolo aperto/chiuso per specie e zona |
| `src/field/` | Motore VTH: legge `../model/vth-v1.json`, combina osservazioni di campo e punti della mappa, scala a 36 |
| `src/map/` | Stile MapLibre, file PMTiles in IndexedDB letti con `FileSource`, lettura dello score in un punto senza mappa |
| `src/diary/` | Database Dexie (spot, valutazioni, uscite, ritrovamenti), registrazione traccia GPS |
| `src/backup/` | Backup cifrato: PBKDF2-SHA256 (600k iterazioni) + AES-GCM 256, gzip, foto incluse |
| `src/views/` | Oggi, Mappa, Campo, Diario, Uscita, Spot, Regole, Altro |
| `public/basemap/` | Font e sprite per la basemap offline Protomaps (licenze nel README della cartella) |

## Scelte da sapere

- **Mappe come file locali.** Lo score VTH e la basemap offline si importano come `.pmtiles` e restano in IndexedDB. Si leggono a pezzi (`FileSource`), quindi funzionano in bosco senza rete e senza service worker che gestisca le range request.
- **Il campo vince sulla mappa.** Ogni parametro osservato sostituisce la stima remota. Il totale si riporta a 36 sul massimo ottenibile con i parametri presenti; sotto 8 parametri la classe è provvisoria (`model.field.minParamsForClass`).
- **Basemap online = qualcuno vede dove guardi.** OpenTopoMap e OSM ricevono le richieste delle tessere. Le tessere viste restano in cache (al massimo 3000, 30 giorni), senza scaricamenti massivi. Per la privacy vera serve la basemap offline.
- **La traccia si registra con l'app aperta.** Il wake lock tiene lo schermo acceso se il telefono lo supporta. A schermo bloccato il browser può fermare il GPS: è un limite delle PWA, non un bug.
- **Foto senza EXIF.** Le foto dei ritrovamenti si ridimensionano a 1600 px e si ricodificano: il GPS nei metadati sparisce.
- **Dati Vue → IndexedDB.** Prima di scrivere, gli oggetti reattivi passano da `plain()`: IndexedDB non sa clonare i Proxy.
