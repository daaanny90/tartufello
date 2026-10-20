# Fase 0 - verifica dei dati (20 ottobre 2026)

Verifica fatta dall'ambiente cloud con rete aperta verso `servizigis`, `geoportale`, `agricoltura`, `mappegis`, `geo`, `servizimoka`, `ambiente` (.regione.emilia-romagna.it) e `inspire-geoportal.ec.europa.eu`. Restano **non raggiungibili da qui**: `agri.regione.emilia-romagna.it` (webGIS CAPP e istituti faunistici), `datacatalog.regione.emilia-romagna.it` (MinERva, carta del pH), `metasfera.regione.emilia-romagna.it` (metadati), `data.europa.eu` (dove rimanda il record INSPIRE), portale Arpae.

I valori verificati sono in `sources.toml` (ogni sorgente ha `status_note` con URL e data). I file scaricati stanno in `data/raw/` (fuori da git).

## Riepilogo

| Sorgente | Esito | Accesso usato | Licenza | Nel build |
|---|---|---|---|---|
| dtm | ok | WCS 1.0.0 `wcs/dtm5x5` (il WCS del brief è dismesso) | CC BY 4.0 | quota |
| dem10 | non trovato | - | - | - |
| suoli | ok | zip open data 1:50.000 + Excel profili | CC BY 4.0 | pH, CaCO3, tessitura |
| ph | da verificare | raster su MinERva (host bloccato qui) | da verificare | no (sostituito dai profili) |
| geologia | ok | zip open data unità 50k (anche WFS) | CC BY 4.0 | roccia madre |
| forestale | ok | shapefile per provincia (sito ambiente) | CC BY 4.0 (note legali del sito) | maschera, tipo, ospiti |
| vegetazione | ok (parziale) | WMS/WFS su https | CC BY 4.0 | no |
| erg5 | da verificare | portale Arpae non raggiungibile | - | no |
| capp | non trovato | webgis su host bloccato | - | no |
| aree_protette | ok | WFS `areeprotette_natura2000` + shapefile | CC BY 4.0 | no (app) |
| aree_tutela_fauna (nuovo) | da verificare | webGIS PFV con export shapefile (host bloccato) | da verificare | no (app) |

## Per sorgente

### DTM (quota)
- **Trovato.** Il WCS del brief `https://servizigis.regione.emilia-romagna.it/wcs/dtm10k_ed2014` risponde ma serve un'immagine dismessa (coverage `1` = "Servizio_dismesso_RDN32_RMD", 4 bande uint8, tutta bianca nel campione). Il catalogo del geoportale indica il servizio nuovo `https://servizigis.regione.emilia-romagna.it/wcs/dtm5x5`, coverage `DTM5X5_RDN32_RMD`. Risponde solo in WCS 1.0.0-1.1.2: float32, 5 m, EPSG:7791, estensione 508200-802800 / 4843000-5002000. Valori plausibili (376-547 m vicino a Calestano).
- Alternativa: 4 quadranti GeoTIFF zippati (ed. 2025, 1,0-1,6 GB l'uno) da `https://mappegis.regione.emilia-romagna.it/archiviogis/DTM/DTM5x5_ed2025_{NO,NE,SO,SE}_7791.zip` (link dalla pagina "DTM 5m x 5m - ultima edizione"). Gli header TIFF letti a distanza danno nodata -9999 e i limiti dei quadranti.
- **Licenza:** CC BY 4.0. È nel PDF di licenza dentro il pacchetto e nel catalogo.
- Il WCS non dichiara il nodata: in config è `nodata = -9999`, preso dai TIFF dello stesso prodotto.

### DEM 10x10
- **Non trovato.** `http://geoportale.regione.emilia-romagna.it/it/download/prodottiraster` ora porta alla home del nuovo geoportale, e nel catalogo "Altimetria" non c'è un DEM 10 m. Il DTM 5x5 via WCS lo rende superfluo.

### Carta dei suoli 1:50.000 (tessitura, CaCO3, pH)
- **Trovato:** `https://mappegis.regione.emilia-romagna.it/moka/ckan/suolo/Carta_Suoli_50k.zip` (Edizione 2021, 13677 delineazioni, EPSG:7791). La copertura è parziale: 78% della regione, 93% del basso Appennino, **37% del medio Appennino**.
- I poligoni **non** hanno attributi di tessitura, CaCO3 o pH. Il pacchetto però contiene `Carta_Suoli50k.xlsx`:
  - `delin_suoli`: suoli di ogni delineazione con percentuale e sito rappresentativo;
  - `delin_siti`: analisi per orizzonte (SABBIA, LIMO, ARGILLA, CALTOT, PHH2O, profondità).
- **Metodo nuovo** (`python -m fiuto_pipeline prepare suoli`): si prende il suolo prevalente della delineazione e il suo sito rappresentativo, poi si fa la media pesata sullo spessore degli orizzonti in 0-30 cm. La classe USDA si ricava da sabbia/limo/argilla. Risultato: 13009 delineazioni su 13677 con valori.
- Verifiche fatte sul dato stesso:
  - **CALTOT è in %**: le mediane per classe descrittiva sono 0,2 (non calcareo), 2,0 (scarsamente), 7,5 (moderatamente), 16 (molto), 26 (fortemente), coerenti con le classi % della legenda regionale;
  - la classe USDA calcolata coincide con il codice di tessitura del dataset (TUSDA) nel **97,8%** di 11453 orizzonti; le differenze sono ai confini tra classi.
- Le carte raster regionali 0-30 cm (`Tessitura_0_30_cm_rst`, `Calcare_totale_0_30_cm_rst`) esistono sul WMS. Dal geoportale non risultano scaricabili; probabilmente sono su MinERva come il pH [da verificare].
- **Licenza:** CC BY 4.0 (catalogo). WFS `wfs/suoli`: HTTP 400. WCS `wcs/suoli`: HTTP 401.

### Carta del pH 0-30 cm
- **Individuata, non scaricata.** Le note illustrative (2a ed. 2023, CC BY 4.0) descrivono 2 raster a 100 m in EPSG:7791 (`pH_0_30.tif`, `pH_0_30_ACC.tif`), scaricabili da MinERva: `https://datacatalog.regione.emilia-romagna.it/catalogCTA/group/suolo`. Quell'host è rifiutato dal proxy di questo ambiente.
- Per ora il pH viene dai profili della carta dei suoli: il build usa la sorgente `ph` se c'è, altrimenti `suoli`.

### Carta geologica (roccia madre)
- **Trovato:** `https://mappegis.regione.emilia-romagna.it/moka/ckan/geologia/Unita_geologiche_50K.zip`. Sono 302 MB, regione intera, Last-Modified 2021-02-15, in "UTMRER" (stessi parametri di EPSG:5659).
- Campi usati: `SIGLA`, `NOME_COMPL`, `DESCRIZION`. La descrizione litologica è presente nel 75% dei poligoni della Val Baganza ma è troncata a 254 caratteri dal formato shapefile.
- Anche WFS 2.0.0 `https://servizigis.regione.emilia-romagna.it/wfs/geologia50k` (GEOJSON, paginazione, EPSG:7791), typename `portale_geologia50k:Unita_geol_50k`.
  - Il layer `Formazioni_geol` ha descrizioni per formazione, ma il filtro BBOX non restituisce nulla e le descrizioni coprono solo le unità che già le hanno.
  - Lo zip 1:10.000 indicato dal catalogo (`Unita_geologiche_10k.zip`) risponde 404.
- **Licenza:** CC BY 4.0 (catalogo).

### Carta forestale regionale
- **Trovato:** shapefile per provincia sulla pagina `https://ambiente.regione.emilia-romagna.it/it/parchi-natura2000/foreste/quadro-conoscitivo/sistema-informativo-regionale/carta-forestale-regionale`. Per Parma: `cartaforestalepr.zip` → `CartaForestale2025PR` (Carta forestale regionale 2025, foto AGEA 2023), 20268 poligoni, EPSG:7791.
- Campi utili: `NOMEUSO`, `COD_TIPO`/`NOMETIPO` (tipi forestali), `COD_CAT`/`NOMECAT`, `PRIMA_SP`/`SPECIE1` e `SECONDA_SP`/`SPECIE2` (specie prevalenti con nome latino).
- WMS `wms/aree_forestali`. WFS `wfs/aree_forestali`: HTTP 401.
- **Licenza:** la pagina del dato non la indica. Le Note legali del sito (`https://ambiente.regione.emilia-romagna.it/it/note-legali`) dicono CC BY 4.0 per contenuti e materiali scaricabili, salvo diversa indicazione. Conviene una conferma scritta.

### Carta della vegetazione
- Copertura parziale confermata: sono carte di singole aree. Nel parmense: Alta Val Parma e Cedra (2002), Boschi di Carrega (1999), Taro (1999), Stirone (2002).
- Risponde su `https://servizigis.regione.emilia-romagna.it/{wms,wfs}/carta_della_vegetazione`; l'URL http del brief qui non si risolve. Non usata.

### ERG5, CAPP
- ERG5: il portale Arpae non è raggiungibile da qui; non serve allo score.
- CAPP: nessun download o WMS nel catalogo; il webgis è su host bloccato. Resta da chiedere alla Regione.

### Aree protette (parchi, Natura 2000)
- **Trovato:** WFS 2.0.0 `https://servizigis.regione.emilia-romagna.it/wfs/areeprotette_natura2000` (EPSG:25832) con `Parchi_Riserve_limiti`, `Parchi_Riserve_zone`, `SIC_ZPS_regionali`, ecc.
- Shapefile su `https://ambiente.regione.emilia-romagna.it/it/parchi-natura2000/consultazione/dati` (parchi e riserve; Natura 2000 aggiornata all'8 luglio 2024).
- **Licenza:** CC BY 4.0 (catalogo).

### Aree di tutela della fauna (nuova)
- **Lo strato esiste.** Una notizia della Regione del 20/11/2024 (`https://agricoltura.regione.emilia-romagna.it/fauna-e-caccia/notizie/2024/disponibile-su-piattaforma-webgis-la-cartografia-degli-istituti-faunistici-pubblici-e-privati`) annuncia il webGIS del Piano faunistico venatorio con esportazione shapefile (EPSG:25832): `https://agri.regione.emilia-romagna.it/MotoreGis/PianoFaunisticoVenatorio/gis.html`.
- Quell'host è rifiutato da qui, quindi va esportato a mano. Non è nel catalogo del geoportale. Licenza da verificare.
- **Norma verificata sul testo coordinato della L.R. 24/1991, art. 15** (PDF su agricoltura.regione.emilia-romagna.it):
  - in oasi, zone di rifugio, ZRC e aziende faunistico-venatorie e agri-turistico-venatorie si cerca con **un solo cane** (c. 1);
  - nelle aziende la raccolta è vietata nei giorni di caccia (c. 4 lett. a);
  - in tutte queste aree è vietata **dal 1/2 al 30/6 in collina** (dal 1/4 al 30/6 in pianura) (c. 4 lett. b).

## Build Val Baganza (`val_baganza_approx`, bbox approssimativo)

Comandi:
```sh
python -m fiuto_pipeline fetch forestale
python -m fiuto_pipeline fetch suoli
python -m fiuto_pipeline prepare suoli
python -m fiuto_pipeline fetch geologia
python -m fiuto_pipeline fetch dtm --aoi val_baganza_approx
python -m fiuto_pipeline build --aoi val_baganza_approx
```
Il DTM sono 42 riquadri, 142 MB. Il build dura circa 20 s.

Output in `data/build/val_baganza_approx/`:
- `vth_val_baganza_approx.pmtiles`: **2,7 MB**, 17533 poligoni, zoom 8-14, 453 tile, tutti verificati contro il contratto. Il metadata ha `warning` "tabelle di lookup in BOZZA" e `aoi_note`.
- `vth_val_baganza_approx.tif` (0,5 MB), `vth_val_baganza_approx.geojsonl` (14 MB), `report.json`, `da_classificare_bedrock.csv`, `da_classificare_forest_type.csv`.

Maschera bosco (`NOMEUSO = 'Bosco'`): **41064 ha**. Disponibilità dei parametri sulle celle in maschera:

| quota | ospiti | pH | CaCO3 | tessitura | roccia madre | tipo di bosco |
|---|---|---|---|---|---|---|
| 100% | 100% | 64,8% | 64,8% | 64,8% | 18,3% | 4,1% |

- Lo score (almeno 4 parametri) c'è sul **64,8%** del bosco. Media 0,86, minimo 0,31.
- **Lo score oggi discrimina poco:**
  - gli ospiti valgono 1 nel 99,5% del bosco (querce, carpino nero e faggio dominano);
  - i suoli sono quasi tutti alcalini e calcarei;
  - roccia madre e tipo di bosco sono quasi tutti non classificati.
- Non classificati: 20 tipi forestali (i più estesi: Boschi di Roverella 12981 ha, Cerrete 8839, Orno-ostrieti 8639, Faggete 4940) e 128 unità geologiche (le più estese: frane quiescenti a2 6133 ha, FYS2 4196, MCS 3228, SCB 2208).

## Tabelle di lookup: bozze

Tutte le righe hanno `note = "BOZZA da rivedere"` e `fonte` con dataset, attributo e testo. Il build lo scrive nel metadata.

- **`suoli_tessitura.csv`** (12 righe): classe USDA → categoria del modello con lo stesso campo `usda` (1:1).
- **`forestale_specie.csv`** (63 specie):
  - `host=1` se il nome latino (o il genere, per le voci "spp.") è in `hostSpecies` del modello: 19 specie;
  - `host=0` se il nome latino è chiaro e non c'è: 41 specie;
  - vuote 3: "Pioppi americani ed ibridi", "Pinus laricio" (forse *P. nigra* subsp. *laricio*), "Nessuna specie identificata".
- **`forestale_vth.csv`** (3 righe): solo i tipi che la carta stessa chiama igrofili o ripariali (SP20X, SP40X, SP50X) → `umidi`. Tutti gli altri restano vuoti (BRIEF §9.4).
- **`geologia_vth.csv`** (11 righe), solo testi chiari:
  - marne: ANT, CTG, CIG, e MMP e RTR dal nome;
  - calcari: CGV, e RCA dal nome;
  - calcari marnosi e marne alla pari → `marne` (classe più bassa, come la convenzione `fizzTest` del modello): CAO, BET, CNL;
  - arenarie a cemento carbonatico → `dolomie` ("altre rocce con calcio"): ARB;
  - restano vuote frane, detriti, depositi alluvionali, argilliti, brecce, ofioliti, e le unità senza descrizione (FYS2, MCS, SCB, FAA…).

## Da decidere (Danny)

1. **Maschera bosco.** Oggi è `NOMEUSO = 'Bosco'`. Esclude 3008 ha di "vegetazione boschiva ed arbustiva in evoluzione" nella valle, più castagneti e noccioleti da frutto e impianti. Va bene?
2. **Tipi forestali → classi VTH.** È la domanda aperta del brief. Senza questa traduzione il parametro resta quasi vuoto. Esempi: Faggete, Cerrete, Orno-ostrieti → "latifoglie fresche"? Roverella (xerofila) → "altri"?
3. **Roccia madre.**
   - Va bene "a cavallo → classe più bassa"?
   - Vanno classificate a mano le unità senza descrizione (FYS2, MCS, SCB, FAA: serve la legenda o le note del foglio).
   - Le frane quiescenti (6133 ha in bosco) come si trattano?
4. **pH dai profili o dal raster.** Il raster regionale a 100 m (DSM e geostatistica) è il prodotto ufficiale; i profili sono un ripiego. Scaricalo da MinERva e mettilo in `[sources.ph] local_path`: il build lo preferisce da solo.
5. **Ospiti.** Il castagno (*Castanea sativa*) non è nella lista del modello: va aggiunto? Se sì, è un cambio del modello (nuova versione). Lo stesso vale per *Pinus laricio*.
6. **CRS di lavoro.** I dati regionali oggi sono in EPSG:7791 o 25832, non più 5659 come dice il brief. La griglia resta in 5659 (si riproietta tutto); si può passare a 7791.
7. **AOI vera.** I confini ufficiali sono scaricabili dal geoportale (`AmbitiAmministrativi2021-25k-RDN2008-UTM32_7791.zip` nell'elenco dei download preconfezionati; non ancora scaricato).

## Da chiedere alla Regione

- Download (o WCS) delle carte raster 0-30 cm di tessitura e calcare totale, e licenza della carta del pH su MinERva.
- Licenza esplicita della Carta forestale regionale (sulla pagina del dato non c'è).
- CAPP Tuber magnatum: download e licenza.
- Istituti faunistici: c'è un servizio WFS o un download stabile oltre all'export dal webGIS? Licenza?
- Descrizioni litologiche delle unità 1:50.000 che ne sono prive (FYS2, MCS, SCB, FAA, MRO1…).

## Cambi al codice fatti in Fase 0

- **HTTP:** ritentativi con attesa crescente (il server chiude connessioni a caso).
- **WCS 1.0.0:**
  - `service.wcs_version`, `wcs_res`, `crs` = CRS nativo;
  - rifiuto dei tile multibanda (immagini RGBA al posto dei valori);
  - `attributes.nodata` per i raster che non lo dichiarano;
  - `capabilities` descrive anche le coverage 1.0.0.
- **`prepare suoli`:** proprietà 0-30 cm dai profili (Excel della carta dei suoli). Nomi di fogli e colonne stanno in `[sources.suoli.prepare]`.
- **Ospiti dalle specie prevalenti:** `hosts_attrs` più `lookups/forestale_specie.csv`. Ospite se almeno una specie lo è; 0 solo se tutte sono note e non ospiti.
- **Bozze nel metadata:** le righe BOZZA nelle tabelle usate finiscono nel `warning` del PMTiles e in `report.json` (`lookup_bozza`).
- **Correzione:** il filtro `mask_where` su Shapefile non trovava nulla se il campo non era tra quelli letti.
- **`--raw-dir`** per isolare i test dalla cache vera.

## Aggiornamento 20/10/2026: modello vth-v2

Decisioni di Danny (vedi `../model/vth-v2.json`, campo `changes`):
- **ospiti fuori dallo score remoto**: valevano 1 sul 99,5% del bosco e non distinguevano nulla; restano nella checklist sul posto. Il build li ignora (niente score, tile, report);
- **tipo di bosco con classi appenniniche**: termofile 3, mesofile 2, umidi 1, altri 0. In `lookups/forestale_vth.csv`:
  - decise: QU, CE, OS → termofile; FA → mesofile; RI10X, RI20X, RI30X → altri; LM10X, LM20X, LM30X, SP20X, SP40X, SP50X → umidi;
  - bozze di estensione: QC, LM50X, LM60X → mesofile; BS30X, BS50X, BS51X → altri;
  - non classificati: CA, PM10X, AB, BS40X.

Build Val Baganza con vth-v2:
- **tipo di bosco**: copertura dal **4,1% al 97,7%** del bosco (termofile 74%, mesofile 12%, altri 7%, umidi 4%);
- **score**: presente sul 64,8% (limite: copertura della carta dei suoli); media 0,857, minimo 0,267. Per decili: 0, 0, 444, 3845, 6892, 7066, 31568, 56633, 116120, 203275 celle;
- **PMTiles**: 3,0 MB, 19840 poligoni.
- Restano non classificati: castagneti (881 ha in bosco) e unità geologiche come frane quiescenti a2 (6133 ha), FYS2 (4196), MCS (3228), SCB (2208).
