# CLAUDE.md

Progetto: **fiuto** (nome provvisorio), app personale per stimare dove cercare tartufo nero (*Tuber aestivum* / *uncinatum*) nell'Appennino parmense.

Il documento di riferimento è il brief, importato qui sotto. Leggilo prima di qualsiasi lavoro: scopo, non-obiettivi, modello, dati e roadmap stanno lì.

@BRIEF.md

## Regole di lavoro

- **Niente dati inventati.** Endpoint, nomi di layer, attributi, licenze: se non sono verificati restano **[da verificare]**. Se qualcosa non torna, ci si ferma e si chiede.
- Quando un **[da verificare]** viene chiarito, si aggiorna `BRIEF.md` con l'esito e la fonte (URL + data), non solo il codice.
- **Privacy prima di tutto.** Niente backend, account, telemetria, analytics, mappe condivise. Le coordinate di uscite e ritrovamenti restano sul dispositivo; escono solo con un export esplicito e cifrato.
- **Regole di raccolta come dati.** Calendario e vincoli normativi vivono in file versionati sotto `rules/` con fonte e data della delibera, mai hardcoded nel codice.
- **Niente precisione finta.** Output dello score a 20-25 m; il DTM a 5 m serve solo per derivare quota e morfologia.
- **VTH è un prior, non la verità.** Le incoerenze note del paper (C/N, CaCO3, numero di siti "alta") sono documentate nel brief: non "correggerle" in silenzio nel codice.
- CRS: dati regionali in EPSG:5659, mappa in EPSG:3857.

## Stack

- `pipeline/`: Python (GDAL, rasterio, geopandas), export GeoTIFF -> MBTiles -> PMTiles.
- `app/`: Vue 3 + TypeScript + Vite, MapLibre GL JS + pmtiles, PWA (vite-plugin-pwa), IndexedDB via Dexie, cifratura export con WebCrypto.

## Stato

Fase 0 (spike dati), nessun codice ancora. Documenti in italiano; identificatori nel codice in inglese, come nel modello dati del brief.
