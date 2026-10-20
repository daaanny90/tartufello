# pipeline/ - dati regionali -> score remoto VTH -> PMTiles

Calcola lo **score remoto VTH** (BRIEF §4.3) su una griglia da 25 m in EPSG:5659 e lo esporta come PMTiles vettoriale (layer `vth`) per l'app. Soglie, categorie, massimi e contratto dei tile stanno **solo** nel modello indicato da `build.toml` (oggi `../model/vth-v2.json`; `vth-v1.json` resta leggibile). I parametri derivati che il modello non elenca come remoti (con v2 gli ospiti) vengono ignorati dal build: niente score, tile o report per loro.

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
  basemap/          mappa offline: rilievo (raster) e base vettoriale (curve, sentieri, strade, acque, località)
scripts/make_synthetic_fixture.py   fixture SINTETICA per i test dell'app
data/               (fuori da git) raw/ = download, build/<aoi>/ = output
```

## Comandi

```sh
.venv/bin/python -m fiuto_pipeline info                       # cosa manca, sorgente per sorgente
.venv/bin/python -m fiuto_pipeline capabilities <sorgente>    # GetCapabilities + Describe*
.venv/bin/python -m fiuto_pipeline capabilities <sorgente> --service wfs --url <URL>   # prova un endpoint nuovo
.venv/bin/python -m fiuto_pipeline fetch <sorgente> [--aoi <nome>] [--method url|wfs|wcs] [--force]
.venv/bin/python -m fiuto_pipeline prepare suoli                # pH/CaCO3/tessitura 0-30 cm dai profili
.venv/bin/python -m fiuto_pipeline build --aoi <nome> [--no-forest-mask] [--no-tiles] [--out DIR]
.venv/bin/python -m fiuto_pipeline basemap --aoi <nome> [--only rilievo|base] [--force] [--out DIR]
```

Opzioni globali: `--sources`, `--aoi-file`, `--build-config`, `--lookups`, `--raw-dir` (cartella dei download, default `data/raw/`). Codici di uscita: 0 ok, 1 errore, 2 sorgente non configurata.

## Stato dei dati (Fase 0 fatta il 2026-10-20)

Esiti, URL, licenze e decisioni aperte sono in **[FASE0.md](FASE0.md)**. In breve: DTM, carta dei suoli, geologia e carta forestale sono scaricabili e usati; il raster del pH sta su MinERva (da scaricare a mano); le tabelle di lookup sono **bozze** da rivedere (il PMTiles lo dichiara nel metadata `warning`). Per rifare il build della Val Baganza:

```sh
.venv/bin/python -m fiuto_pipeline fetch forestale
.venv/bin/python -m fiuto_pipeline fetch suoli && .venv/bin/python -m fiuto_pipeline prepare suoli
.venv/bin/python -m fiuto_pipeline fetch geologia
.venv/bin/python -m fiuto_pipeline fetch dtm --aoi val_baganza_approx     # WCS 1.0.0, riquadri da 5 km
.venv/bin/python -m fiuto_pipeline build --aoi val_baganza_approx
```

## Come si è fatta la Fase 0 (per ripeterla su un dato nuovo)

1. **Stato.** `python -m fiuto_pipeline info` dice per ogni sorgente stato, dati in cache, cosa manca.
2. **AOI.** `aoi.toml` ha due rettangoli scritti a mano e approssimativi (`val_baganza_approx`, `parma_approx`). Con un confine vero in un file usa `path = "..."`: il build calcola solo dentro il poligono.
3. **Servizi.** `capabilities <sorgente>` (o `--service wfs|wcs --url <URL>` per un endpoint nuovo) stampa layer, attributi, coverage, CRS e formati; gli XML restano in `data/raw/<sorgente>/`. I WMS danno solo immagini: per il calcolo servono WFS, WCS di valori o download.
4. **Download.** Gli open data regionali hanno spesso uno zip diretto (`url_opendata` nel catalogo del geoportale, licenza nella stessa voce): mettilo in `endpoints.download` e fai `fetch <sorgente>`. Per WFS: `endpoints.wfs`, `service.wfs_typename`, `fetch --aoi`. Per WCS: vedi le note sotto.
5. **Attributi.** Layer e nomi degli attributi in `[*.attributes]` (visti nel file o nel DescribeFeatureType), mai a memoria. Se i valori sono in un'altra scala (es. pH in decimi) usa `value_scale`: la pipeline si ferma se trova valori fuori range.
6. **Carta forestale.** Senza di lei non c'è maschera bosco e il build si ferma (lo score vale solo in bosco). Per una prova senza: `build --no-forest-mask` (scritto nel metadata come avviso).
7. **Primo build, tabelle vuote.** `python -m fiuto_pipeline build --aoi val_baganza_approx`. Con le tabelle ancora vuote roccia/tessitura/bosco restano non disponibili, ma il build scrive `data/build/<aoi>/da_classificare_<param>.csv` con **tutti i valori trovati nei dati**, nome e superficie (totale e in bosco), già con le colonne della tabella di lookup.
8. **Riempire le tabelle** in `lookups/` partendo da quei CSV, dalle unità più estese in bosco. Con prudenza (BRIEF §9.3-9.4): `fonte` dice da dove viene ogni scelta; una cella vuota vuol dire "non classificato", meglio di una classe tirata a indovinare.
9. **Rilanciare il build.** Output in `data/build/<aoi>/`:
   - `vth_<aoi>.tif`: GeoTIFF EPSG:5659, bande `score_x1000, pts, max, n, mask` + un parametro per banda (nodata 65535), da guardare in QGIS sopra il WMS;
   - `report.json`: disponibilità % di ogni parametro in maschera, valori non classificati con superficie, sorgenti con stato di verifica, modello, data;
   - `vth_<aoi>.geojsonl` (EPSG:4326) e `vth_<aoi>.pmtiles`: quest'ultimo si importa nell'app da Impostazioni.
10. **Chiudere i [da verificare].** Quando un dato è controllato davvero: `status = "ok"` in `sources.toml` e l'esito con URL e data in `BRIEF.md` (CLAUDE.md). Lo stato finisce nel metadata del PMTiles (`sources[].verified`).

Note pratiche emerse in Fase 0:
- WCS di ArcGIS Server: spesso solo 1.0.0-1.1.x. In `[*.service]`: `wcs_version = "1.0.0"`, `wcs_res`, e `crs` = CRS nativo della coverage. Un tile a più bande (RGB/RGBA) viene rifiutato: è un'immagine, non valori. Se il GeoTIFF non dichiara il nodata, usa `attributes.nodata`.
- Carta forestale: ospiti dalle specie prevalenti con `hosts_attrs = ["PRIMA_SP", "SECONDA_SP"]` e `lookups/forestale_specie.csv`; ospite se almeno una specie lo è, 0 solo se tutte sono note e non ospiti. Con vth-v2 gli ospiti non sono più nello score remoto (si valutano sul posto): il calcolo resta, ma il build lo ignora.
- Carta dei suoli: i poligoni non hanno proprietà; `prepare suoli` le ricava dall'Excel del pacchetto (suolo prevalente, profilo rappresentativo, media pesata 0-30 cm, triangolo USDA). Nomi di fogli e colonne in `[sources.suoli.prepare]`.
- Righe di lookup con nota "BOZZA" finiscono nel `warning` del metadata PMTiles e in `report.json` (`lookup_bozza`).

## Score

Per ogni cella nella maschera bosco: `pts` = somma dei punti dei parametri remoti disponibili, `max` = somma dei loro massimi remoti dal modello (con vth-v1 gli ospiti valgono al massimo 1; con vth-v2 sono fuori), `n` = quanti sono. `score = pts / max` solo se `n >= remote.minParams` (4), arrotondato a 3 decimali per eccesso a metà (0,3125 -> 0,313). I valori numerici si confrontano dopo un arrotondamento a 6 decimali, così 7,2 salvato in float32 (7,1999998) non perde il punto.

## Tile

- Poligoni = aree connesse con la stessa combinazione di punti per parametro; proprietà come da `tiles` nel modello: chiave assente se il parametro non è disponibile, `score` assente sotto `minParams`. Celle fuori bosco: nessuna feature.
- Scrittura con il driver **PMTiles di GDAL** (via pyogrio; verificato con GDAL 3.12.4 delle wheel). Il driver accetta solo NAME/DESCRIPTION come metadata, quindi il file viene riscritto con il pacchetto `pmtiles` aggiungendo `model`, `built`, `aoi`, `sources` (più `mask`, `cell_size_m`, `generator`, eventuale `aoi_note`/`warning`). I tile restano gli stessi.
- Ripieghi automatici: GDAL senza PMTiles -> MBTiles di GDAL + `pmtiles` per la conversione; senza nemmeno MBTiles -> solo GeoJSONSeq e il comando `tippecanoe` da lanciare a mano (o `go-pmtiles`), metadata da aggiungere a parte.
- Zoom 8-14 (`build.toml`). Semplificazione del driver MVT `SIMPLIFICATION = 1` unità di tile (1/4096 del lato): circa 27 m a z8, 1,7 m a z12, 0,4 m a z14 alla latitudine di Parma, quindi sotto la cella dove si guarda da vicino.
- Nota per l'app: GDAL scrive `score` 0 e 1 come interi MVT (in JS è lo stesso numero).
- Dopo la scrittura il file viene riletto (GDAL + decoder MVT interno) e controllato contro il contratto: `pts`, `max`, `n` coerenti con i parametri presenti, `score` = `pts/max`.

## Basemap offline (`basemap`)

Prima serve il DTM in cache (`fetch dtm --aoi <nome>`); sentieri e DBTR li scarica il comando stesso (cache in `data/raw/sentieri/`, `data/raw/dbtr/rest/`, `data/raw/dbtr_sentieri/rest/`). Scrive in `data/build/<aoi>/`:

- `rilievo_<aoi>.pmtiles`: PMTiles **raster**. DTM 5x5 mediato a 10 m, ombreggiatura di Horn (sole a 315° e 45°, pianura = grigio 180), riproiettato in EPSG:3857 alla risoluzione di z15, tile WEBP qualità 80 (PNG se GDAL non ha WEBP) con alfa (nodata trasparente; i tile pieni escono RGB). Il driver PMTiles di GDAL non scrive raster: si passa da MBTiles (overview con media) e `pmtiles.convert`. Con un'AOI di pochi km GDAL salta le overview più piccole e i primi zoom mancano (il report lo dice).
- `base_<aoi>.pmtiles`: PMTiles **vettoriale**, z10-15, metadata `fiuto_basemap: true`, `aoi`, `attribution`, `sources`, eventuale `missing` (layer non scritti e perché). Layer e proprietà:
  - `contours`: `ele` (intero, m), `major` (bool, ogni 50 m). Curve ogni 10 m da DTM a 10 m lisciato (binomiale 5x5), semplificate a 2 m, scartate sotto i 100 m. Sotto z13 solo le maggiori.
  - `trails`: `name`, `ref` (numero), `kind` (sigla di classificazione, es. SE), `difficulty` (es. T, E, EE) dalla rete escursionistica regionale.
  - `roads`: `kind` = `strada` (DBTR EST), `carrareccia` (DBTR EVS, viabilità mista secondaria: interpretazione da verificare), `sentiero` (DBTR SEN). Sotto z12 solo `strada`.
  - `water`: `name` (se c'è) dai corsi d'acqua naturali DBTR (FIU).
  - `places`: `name`, `kind` (tipo di località, es. "frazione") dalle località abitate puntuali DBTR (LAB).
- `basemap_<aoi>.json`: report con dimensioni, conteggi, sorgenti e mancanze.

Il driver PMTiles di GDAL scrive un layer per file: si scrive un PMTiles per layer (o per fascia di zoom) e poi si uniscono i tile concatenando gli MVT. Due fasce dello stesso layer devono avere zoom disgiunti (controllato).

## Fixture sintetica per l'app

```sh
.venv/bin/python scripts/make_synthetic_fixture.py
```

Scrive `../app/e2e/fixtures/synthetic-vth.pmtiles`: **dati finti**, blocchi disegnati a mano su lon 10,0-10,1 / lat 44,6-44,7, metadata `"synthetic": true`, passati per lo stesso codice di export. Data `built` fissa, così il file non cambia a ogni rigenerazione.
