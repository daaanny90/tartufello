# fiuto, app

PWA in Vue 3 + TypeScript + Vite. Gira tutta sul telefono: niente server, niente account.

## Comandi

```sh
npm install
npm run dev        # sviluppo
npm test           # unit test (Vitest)
npm run build      # typecheck + build di produzione in dist/
npm run e2e        # smoke test sul build, con Chromium locale e GPS simulato
npm run e2e:offline  # scarica la zona pubblicata, stacca la rete, la mappa deve funzionare
```

`npm run e2e` vuole il build già fatto e Chromium in `/opt/pw-browsers/chromium` (o `CHROMIUM_PATH`). Usa la fixture sintetica `e2e/fixtures/synthetic-vth.pmtiles` se c'è; le schermate finiscono in `e2e/screenshots/` (o `SCREENSHOTS`).

## Pubblicazione

Il workflow `.github/workflows/pages.yml` fa test e build a ogni push sul branch di default e pubblica su GitHub Pages (`https://<utente>.github.io/<repo>/`). La prima volta va abilitato a mano: Settings → Pages → Source: **GitHub Actions**. Su repo privato Pages richiede GitHub Pro.

Il build in sottocartella si prova in locale con `FIUTO_BASE=/tartufello/ npm run build` e `FIUTO_BASE=/tartufello/ npm run e2e`.

In alternativa va bene qualsiasi hosting statico in HTTPS (service worker e GPS lo richiedono), anche il server di casa.

### Mappe pubblicate con l'app

`node scripts/publish-map.mjs <file.pmtiles> <id> "<titolo>" "<zona>"` copia un file della pipeline (score, mappa di base o rilievo: lo riconosce da solo) in `public/mappe/` e aggiorna `index.json`. In Altro, **Pronta per il campo → Scarica tutto** porta nel telefono tutti i file della zona e passa lo sfondo su offline. I file sintetici vengono rifiutati. Sono dati derivati da open data CC BY della Regione, senza niente di personale: spot, tracce e ritrovamenti non lasciano mai il telefono.

## Struttura

| Cartella | Cosa fa |
|---|---|
| `src/rules/` | Calendario ER 2026-2030 come dati (`er-calendar-2026-2030.json`) e calcolo aperto/chiuso per specie e zona; esche avvelenate (`esche-avvelenate.json`): primo intervento e obblighi di segnalazione, ancora da verificare |
| `src/field/` | Motore VTH: legge `../model/vth-v2.json`, combina osservazioni di campo e punti della mappa, scala a 36 |
| `src/map/` | Stile MapLibre, file PMTiles in IndexedDB letti con `FileSource`, lettura dello score in un punto senza mappa |
| `src/diary/` | Database Dexie (spot, valutazioni, uscite, ritrovamenti), registrazione traccia GPS, avviso vicino agli spot pericolo (`danger.ts`) |
| `src/backup/` | Backup cifrato: PBKDF2-SHA256 (600k iterazioni) + AES-GCM 256, gzip, foto incluse |
| `src/views/` | Oggi, Mappa, Campo, Diario, Uscita, Spot, Regole, Emergenza, Altro |
| `public/basemap/` | Font e sprite per la basemap offline Protomaps (licenze nel README della cartella) |

## Scelte da sapere

- **Mappe come file locali.** Lo score VTH e la basemap offline si importano come `.pmtiles` e restano in IndexedDB. Si leggono a pezzi (`FileSource`), quindi funzionano in bosco senza rete e senza service worker che gestisca le range request.
- **Il campo vince sulla mappa.** Ogni parametro osservato sostituisce la stima remota. Il totale si riporta a 36 sul massimo ottenibile con i parametri presenti; sotto 8 parametri la classe è provvisoria (`model.field.minParamsForClass`).
- **Basemap online = qualcuno vede dove guardi.** OpenTopoMap e OSM ricevono le richieste delle tessere. Le tessere viste restano in cache (al massimo 3000, 30 giorni), senza scaricamenti massivi. Per la privacy vera serve la basemap offline.
- **La traccia si registra con l'app aperta.** Il wake lock tiene lo schermo acceso se il telefono lo supporta. A schermo bloccato il browser può fermare il GPS: è un limite delle PWA, non un bug.
- **Avviso pericolo.** Scatta entro 300 m da uno spot "pericolo" e si riarma solo oltre 400 m, così il GPS che balla non fa vibrare a ripetizione. Ignora le letture peggiori di 200 m. Gira finché il GPS è acceso (uscita o mappa aperta). Uno spot appena segnato dove sei entra in silenzio.
- **Foto senza EXIF.** Le foto dei ritrovamenti si ridimensionano a 1600 px e si ricodificano: il GPS nei metadati sparisce.
- **Dati Vue → IndexedDB.** Prima di scrivere, gli oggetti reattivi passano da `plain()`: IndexedDB non sa clonare i Proxy.
