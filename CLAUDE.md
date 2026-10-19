# CLAUDE.md

Progetto: **fiuto** (nome provvisorio), app personale per stimare dove cercare tartufo nero (*Tuber aestivum* / *uncinatum*) nell'Appennino parmense.

Il documento di riferimento è il brief, importato qui sotto. Leggilo prima di qualsiasi lavoro: scopo, non-obiettivi, modello, dati e roadmap stanno lì.

@BRIEF.md

## Regole di lavoro

- **Niente dati inventati.** Endpoint, nomi di layer, attributi, licenze: se non sono verificati restano **[da verificare]**. Se qualcosa non torna, ci si ferma e si chiede.
- Quando un **[da verificare]** viene chiarito, si aggiorna `BRIEF.md` con l'esito e la fonte (URL + data), non solo il codice.
- **Privacy prima di tutto.** Niente backend, account, telemetria, analytics, mappe condivise. Le coordinate di uscite e ritrovamenti restano sul dispositivo; escono solo con un export esplicito e cifrato.
- **Regole di raccolta come dati.** Calendario e vincoli normativi vivono in file versionati (`app/src/rules/er-calendar-2026-2030.json`) con fonte e data della delibera, mai hardcoded nel codice.
- **Il modello è uno solo.** Soglie, classi, ospiti e contratto dei tile stanno in `model/vth-v1.json`, letto da pipeline e app. Non duplicare soglie nel codice; se cambia una soglia, nuova versione del modello.
- **Niente precisione finta.** Output dello score a 20-25 m; il DTM a 5 m serve solo per derivare quota e morfologia.
- **VTH è un prior, non la verità.** Le incoerenze note del paper (C/N, CaCO3, numero di siti "alta") sono documentate nel brief: non "correggerle" in silenzio nel codice.
- CRS: dati regionali in EPSG:5659, mappa in EPSG:3857.

## Struttura e comandi

| Cartella | Cosa | Verifica |
|---|---|---|
| `model/` | Modello VTH condiviso | letto dai test di entrambe le parti |
| `pipeline/` | Python: dati regionali -> score remoto -> PMTiles vettoriale (layer `vth`). Dettagli e Fase 0 in `pipeline/README.md` | `cd pipeline && .venv/bin/python -m pytest` |
| `app/` | PWA Vue 3 + TS + Vite, MapLibre 6 + pmtiles, Dexie, WebCrypto. Dettagli in `app/README.md` | `cd app && npm test && npm run build && npm run e2e` |

Prima di un push: i test della parte toccata devono passare; se tocchi `model/`, girano entrambe le suite. `npm run e2e` usa la fixture sintetica `app/e2e/fixtures/synthetic-vth.pmtiles`, generata da `pipeline/scripts/make_synthetic_fixture.py`: se cambia il contratto dei tile, rigenerala.

## Stato

- App (Fase 1 lato app e Fase 2): fatta e testata, in attesa di dati veri.
- Pipeline: fatta e testata su dati sintetici. Tutti i dataset regionali sono ancora **[da verificare]**: la Fase 0 non è iniziata.
- Il proxy dell'ambiente cloud blocca `*.regione.emilia-romagna.it`: la Fase 0 si fa da un computer normale o dopo aver allargato la rete dell'ambiente.

Documenti in italiano; identificatori nel codice in inglese, come nel modello dati del brief.
