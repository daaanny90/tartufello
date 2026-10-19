# pipeline/ - dati regionali -> score remoto VTH -> PMTiles

Calcola lo **score remoto VTH** (BRIEF §4.3) su una griglia da 25 m in EPSG:5659 e lo esporta come PMTiles vettoriale (layer `vth`) per l'app. Soglie, categorie, massimi e contratto dei tile stanno **solo** in `../model/vth-v1.json`.

Regola di casa: niente endpoint, layer, attributi o codici inventati. Quello che non è verificato resta vuoto in `sources.toml` con stato `da verificare`, e la pipeline si rifiuta di partire dicendo cosa controllare.

## Installazione

Python 3.11+ (provato con 3.13). Le wheel di rasterio e pyogrio includono GDAL: non serve installarlo a parte.

```sh
cd pipeline
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/python -m pytest          # tutti offline, dati sintetici
```

## Struttura

```
sources.toml        sorgenti (brief §5): endpoint, stato, local_path, identificativi
aoi.toml            aree di lavoro (bbox 4326/5659 o file GeoJSON/GPKG)
build.toml          griglia (EPSG:5659, 20-25 m) ed export (zoom, semplificazione)
lookups/*.csv       tabelle valore ER -> classe VTH, da riempire a mano
fiuto_pipeline/
  fetch/            capabilities, scarico url/WFS/WCS con cache in data/raw/
  derive/           un parametro VTH per funzione (uint8, 255 = non disponibile)
  score/            somma normalizzata, GeoTIFF multibanda, report
  export/           poligoni per combinazione di punti -> GeoJSONSeq + PMTiles
scripts/make_synthetic_fixture.py   fixture SINTETICA per i test dell'app
data/               (fuori da git) raw/ = download, build/<aoi>/ = output
```

## Comandi

```sh
.venv/bin/python -m fiuto_pipeline info                       # cosa manca, sorgente per sorgente
.venv/bin/python -m fiuto_pipeline capabilities <sorgente>    # GetCapabilities + Describe*
.venv/bin/python -m fiuto_pipeline capabilities <sorgente> --service wfs --url <URL>   # prova un endpoint nuovo
.venv/bin/python -m fiuto_pipeline fetch <sorgente> [--aoi <nome>] [--method url|wfs|wcs] [--force]
.venv/bin/python -m fiuto_pipeline build --aoi <nome> [--no-forest-mask] [--no-tiles] [--out DIR]
```

Codici di uscita: 0 ok, 1 errore, 2 sorgente non configurata.

## Fase 0 passo per passo (Val Baganza)

1. **Stato iniziale.** `python -m fiuto_pipeline info`: tutto è `[da verificare]`, nessun parametro pronto.
2. **AOI.** `aoi.toml` ha due rettangoli scritti a mano e approssimativi (`val_baganza_approx`, `parma_approx`). Appena hai il confine vero, mettilo in un file e usa `path = "..."`: il build calcola solo dentro il poligono.
3. **DTM (quota).**
   - `python -m fiuto_pipeline capabilities dtm --service wcs` stampa coverage, assi (`axisLabels`), CRS (`srsName`) e formati. Gli XML restano in `data/raw/dtm/`.
   - Riempi in `[sources.dtm.service]`: `wcs_coverage_id`, `wcs_axis_x`, `wcs_axis_y`, `wcs_format` (un GeoTIFF). Controlla che `srsName` sia EPSG:5659.
   - `python -m fiuto_pipeline fetch dtm --aoi val_baganza_approx` scarica riquadri da 5 km in `data/raw/dtm/wcs/...` (il build li legge tutti).
   - In alternativa: DEM 10x10 dalla pagina in `[sources.dem10.endpoints] page`, estrai lo zip e metti la cartella in `local_path`.
4. **Suoli e geologia.** I WMS del brief danno solo immagini: `capabilities suoli` / `capabilities geologia` servono a leggere i nomi dei layer. Per il calcolo serve un vettore:
   - cerca un WFS o un download nel geoportale/webgis (link in `sources.toml`); se trovi un WFS: `capabilities geologia --service wfs --url <URL>` mostra feature type e attributi, poi scrivi `endpoints.wfs`, `service.wfs_typename` e fai `fetch geologia --aoi val_baganza_approx`;
   - oppure scarica a mano e imposta `local_path`.
   - Poi gli attributi: `suoli.attributes.texture_attr`, `caco3_attr` (solo se numerico in %), `geologia.attributes.unit_code_attr` (e `unit_name_attr` per i report).
5. **pH.** Leggi la nota (`[sources.ph.endpoints] note`), scarica il dato, `local_path`. Raster o vettore (`ph_attr`). Se i valori sono in decimi imposta `value_scale = 0.1`: la pipeline si ferma se trova valori fuori 2-11.
6. **Carta forestale.** Senza di lei non c'è maschera bosco e il build si ferma (lo score vale solo in bosco). `local_path`, `forest_type_attr`, e `mask_where` se il layer contiene anche poligoni non boscati. Per una prova senza: `build --no-forest-mask` (scritto nel metadata come avviso).
7. **Primo build, tabelle vuote.** `python -m fiuto_pipeline build --aoi val_baganza_approx`. Con le tabelle ancora vuote roccia/tessitura/bosco restano non disponibili, ma il build scrive `data/build/<aoi>/da_classificare_<param>.csv` con **tutti i valori trovati nei dati**, nome e superficie (totale e in bosco), già con le colonne della tabella di lookup.
8. **Riempire le tabelle** in `lookups/` partendo da quei CSV, dalle unità più estese in bosco. Con prudenza (BRIEF §9.3-9.4): `fonte` dice da dove viene ogni scelta; una cella vuota vuol dire "non classificato", meglio di una classe tirata a indovinare.
9. **Rilanciare il build.** Output in `data/build/<aoi>/`:
   - `vth_<aoi>.tif`: GeoTIFF EPSG:5659, bande `score_x1000, pts, max, n, mask` + un parametro per banda (nodata 65535), da guardare in QGIS sopra il WMS;
   - `report.json`: disponibilità % di ogni parametro in maschera, valori non classificati con superficie, sorgenti con stato di verifica, modello, data;
   - `vth_<aoi>.geojsonl` (EPSG:4326) e `vth_<aoi>.pmtiles`: quest'ultimo si importa nell'app da Impostazioni.
10. **Chiudere i [da verificare].** Quando un dato è controllato davvero: `status = "ok"` in `sources.toml` e l'esito con URL e data in `BRIEF.md` (CLAUDE.md). Lo stato finisce nel metadata del PMTiles (`sources[].verified`).

## Score

Per ogni cella nella maschera bosco: `pts` = somma dei punti dei parametri remoti disponibili, `max` = somma dei loro massimi remoti dal modello (ospiti: 1), `n` = quanti sono. `score = pts / max` solo se `n >= remote.minParams` (4), arrotondato a 3 decimali per eccesso a metà (0,3125 -> 0,313). I valori numerici si confrontano dopo un arrotondamento a 6 decimali, così 7,2 salvato in float32 (7,1999998) non perde il punto.

## Tile

- Poligoni = aree connesse con la stessa combinazione di punti per parametro; proprietà come da `tiles` nel modello: chiave assente se il parametro non è disponibile, `score` assente sotto `minParams`. Celle fuori bosco: nessuna feature.
- Scrittura con il driver **PMTiles di GDAL** (via pyogrio; verificato con GDAL 3.12.4 delle wheel). Il driver accetta solo NAME/DESCRIPTION come metadata, quindi il file viene riscritto con il pacchetto `pmtiles` aggiungendo `model`, `built`, `aoi`, `sources` (più `mask`, `cell_size_m`, `generator`, eventuale `aoi_note`/`warning`). I tile restano gli stessi.
- Ripieghi automatici: GDAL senza PMTiles -> MBTiles di GDAL + `pmtiles` per la conversione; senza nemmeno MBTiles -> solo GeoJSONSeq e il comando `tippecanoe` da lanciare a mano (o `go-pmtiles`), metadata da aggiungere a parte.
- Zoom 8-14 (`build.toml`). Semplificazione del driver MVT `SIMPLIFICATION = 1` unità di tile (1/4096 del lato): circa 27 m a z8, 1,7 m a z12, 0,4 m a z14 alla latitudine di Parma, quindi sotto la cella dove si guarda da vicino.
- Nota per l'app: GDAL scrive `score` 0 e 1 come interi MVT (in JS è lo stesso numero).
- Dopo la scrittura il file viene riletto (GDAL + decoder MVT interno) e controllato contro il contratto: `pts`, `max`, `n` coerenti con i parametri presenti, `score` = `pts/max`.

## Fixture sintetica per l'app

```sh
.venv/bin/python scripts/make_synthetic_fixture.py
```

Scrive `../app/e2e/fixtures/synthetic-vth.pmtiles`: **dati finti**, blocchi disegnati a mano su lon 10,0-10,1 / lat 44,6-44,7, metadata `"synthetic": true`, passati per lo stesso codice di export. Data `built` fissa, così il file non cambia a ogni rigenerazione.
