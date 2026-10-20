# CLAUDE.md

Progetto: **fiuto** (nome provvisorio), app personale per stimare dove cercare tartufo nero (*Tuber aestivum* / *uncinatum*) nell'Appennino parmense.

Il documento di riferimento è il brief, importato qui sotto. Leggilo prima di qualsiasi lavoro: scopo, non-obiettivi, modello, dati e roadmap stanno lì.

@BRIEF.md

## Regole di lavoro

- **Niente dati inventati.** Endpoint, nomi di layer, attributi, licenze: se non sono verificati restano **[da verificare]**. Se qualcosa non torna, ci si ferma e si chiede.
- Quando un **[da verificare]** viene chiarito, si aggiorna `BRIEF.md` con l'esito e la fonte (URL + data), non solo il codice.
- **Privacy prima di tutto.** Niente backend, account, telemetria, analytics, mappe condivise. Le coordinate di uscite e ritrovamenti restano sul dispositivo; escono solo con un export esplicito e cifrato.
- **Regole di raccolta come dati.** Calendario e vincoli normativi vivono in file versionati (`app/src/rules/er-calendar-2026-2030.json`) con fonte e data della delibera, mai hardcoded nel codice.
- **Il modello è uno solo.** Soglie, classi, ospiti e contratto dei tile stanno in `model/vth-v2.json` (versione corrente; `vth-v1.json` resta per storia), letto da pipeline e app. Non duplicare soglie nel codice; se cambia una soglia, nuova versione del modello.
- **Niente precisione finta.** Output dello score a 20-25 m; il DTM a 5 m serve solo per derivare quota e morfologia.
- **VTH è un prior, non la verità.** Le incoerenze note del paper (C/N, CaCO3, numero di siti "alta") sono documentate nel brief: non "correggerle" in silenzio nel codice.
- CRS: griglia di lavoro EPSG:5659; i dati regionali arrivano anche in EPSG:7791 o 25832 e si riproiettano. Mappa in EPSG:3857.

## Struttura e comandi

| Cartella | Cosa | Verifica |
|---|---|---|
| `model/` | Modello VTH condiviso (corrente: `vth-v2.json`) | letto dai test di entrambe le parti |
| `pipeline/` | Python: dati regionali -> score remoto -> PMTiles vettoriale (layer `vth`). Dettagli e Fase 0 in `pipeline/README.md` | `cd pipeline && .venv/bin/python -m pytest` |
| `app/` | PWA Vue 3 + TS + Vite, MapLibre 6 + pmtiles, Dexie, WebCrypto. Dettagli in `app/README.md` | `cd app && npm test && npm run build && npm run e2e` |
| `.github/workflows/pages.yml` | Test, build e pubblicazione su GitHub Pages dal branch di default | gira da solo a ogni push su `app/` o `model/` |

Prima di un push: i test della parte toccata devono passare; se tocchi `model/`, girano entrambe le suite. `npm run e2e` usa la fixture sintetica `app/e2e/fixtures/synthetic-vth.pmtiles`, generata da `pipeline/scripts/make_synthetic_fixture.py`: se cambia il contratto dei tile, rigenerala.

## Stato

- App (Fase 1 lato app e Fase 2): fatta e testata, pubblicata su https://daaanny90.github.io/tartufello/ (repo pubblico dal 20/10/2026). Calendario verificato sulla delibera, regole della L.R. 24/1991 come dati.
- Pipeline: Fase 0 fatta (esiti in `BRIEF.md` §12 e `pipeline/FASE0.md`), modello vth-v2. Score reale della Val Baganza pubblicato con l'app (`app/public/mappe/`). Distingue poco: un quarto del bosco con score vale esattamente 1. La roccia madre è classificata solo sul 18% e alcune righe di lookup sono ancora BOZZA.
- Host ancora bloccati dal proxy dell'ambiente cloud: `agri.regione.emilia-romagna.it` (istituti faunistici, CAPP) e `datacatalog.regione.emilia-romagna.it` (raster del pH). Vanno aggiunti agli Allowed domains o scaricati a mano.

Documenti in italiano; identificatori nel codice in inglese, come nel modello dati del brief.
