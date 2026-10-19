# Brief: app per la cerca del tartufo nero (nome provvisorio: "fiuto")

> Da mettere nella root del repo come `BRIEF.md` e richiamare da `CLAUDE.md`.
> Stato: idea, nessun codice. Scritto il 19 ottobre 2026.
> Tutto ciò che è marcato **[da verificare]** non è stato confermato: niente endpoint inventati, se qualcosa non torna si chiede.

## 1. Cosa vogliamo

Un'app personale che risponda a una domanda sola: **dove ha senso portare il cane a cercare tartufo nero nell'Appennino parmense**.

Le app che esistono già (FunghiMapp, Bosco Mio, Truffle Map) sono diari privati: segni dove hai trovato. Nessuna, tra quelle viste, stima dove cercare. Il valore di questa app sta lì:

1. una **mappa di idoneità** calcolata in anticipo da open data regionali (suolo, geologia, quota, bosco);
2. una **valutazione sul posto** con una checklist che aggiunge quello che dai dati non si vede (struttura del bosco, piante ospiti, orchidee, insetti);
3. un **diario privato** di uscite e ritrovamenti che, stagione dopo stagione, serve a ricalibrare il modello.

Utente unico all'inizio: io (Danny), Parma, con una Lagotto Romagnolo in arrivo a gennaio 2027.

## 2. Non-obiettivi (MVP)

- Niente mappa condivisa o social. I tartufai custodiscono i posti e la Regione stessa lo cita come il motivo per cui i dati di presenza sono scarsi. Una mappa condivisa morirebbe subito.
- Niente backend, niente account, niente telemetria.
- Niente marketplace, niente riconoscimento immagini dei tartufi.
- Niente pretesa di prevedere il singolo tartufo: il modello restringe le zone, l'ultimo metro lo fa il cane.

## 3. Specie target e regole

Target: **Tuber aestivum**, che in Emilia-Romagna si raccoglie in due forme. Il calendario regionale 2026-2030 scrive esplicitamente `Tuber uncinatum (= Tuber aestivum)`: il "nero di Fragno" della Val Baganza è uncinatum, quindi stessa specie dello scorzone estivo. Un solo modello copre entrambe le stagioni.

Calendario ER vigente 2026-2030 (L.R. 24/1991 art. 13, DGR n. 137 del 02/02/2026):

| Specie | Periodo |
|---|---|
| T. uncinatum (= T. aestivum) | 1 ott - 31 gen, tutte le zone |
| T. aestivum (estivo) | 1 giu - 31 lug pianura; 1 giu - 15 ago collina |
| T. magnatum (bianco) | 1 ott - 20 gen |
| T. melanosporum | 1 nov - 31 mar |
| T. brumale (e var. moschatum) | 1 dic - 30 apr |
| T. borchii (= albidum, bianchetto) | 1 dic - 30 apr |
| T. macrosporum, T. mesentericum | 1 ott - 20 gen |

Sospensione totale di ricerca e raccolta: **1-31 maggio** e **16 agosto - 30 settembre**.

Regole da riflettere nell'app:
- Serve il **tesserino di idoneità** (L.R. 24/1991, art. 8) più la tassa di concessione annuale (art. 11).
- Le tartufaie **coltivate o controllate** con tabella regionale ("raccolta riservata") sono off-limits. Non esiste (che sappia) un layer centrale: si gestiscono come segnalazione manuale sul campo.
- Nelle **aree protette** valgono regolamenti propri (L.R. 24/1991 art. 15 e 21, più i regolamenti dei parchi). **[da verificare]** layer dei confini parchi/Natura 2000 dal geoportale.

Il calendario va in un file dati versionato (`rules/er-calendar-2026-2030.json`) con fonte e data, perché cambia con le delibere (l'ha già fatto nel 2022, 2024 e 2026).

Conseguenza pratica sui tempi: la prima finestra di test reale non è l'autunno 2027, è lo **scorzone estivo da giugno 2027** (collina, fino al 15 agosto).

## 4. Il modello

Due fonti di metodo, entrambe pubblicate.

### 4.1 Virtual Truffle Hunting (VTH), per T. aestivum

Rosa-Gruszecka, Hilszczańska, Pacioni, *Forests* 2021, 12(9), 1239, doi:10.3390/f12091239, licenza CC BY. Esiste anche un loro software (eseguibile Windows su GitHub, `AleksandraRosa/Virtual-Truffle-Hunting`).

12 parametri, ciascuno 0-3 punti, massimo 36. Classi: 31-36 alta, 25-30 media, 19-24 bassa, sotto 19 nulla. Testato su 20 siti in Polonia: in tutti i siti classificati "alta" lo scorzone è stato trovato (il testo dice cinque siti, le tabelle ne mostrano tre a 34 punti: altra piccola incoerenza del paper).

| Parametro | 3 pt | 2 pt | 1 pt | 0 pt | Fonte da noi |
|---|---|---|---|---|---|
| Roccia madre | calcari, calcari marnosi, gessi, creta, oolite... | marne, travertino, terra rossa... | dolomia, scisti marnosi, altre rocce con calcio | rocce senza calcio | carta geologica ER + tabella di lookup da costruire |
| pH (H2O) | ≥ 7,2 | 6,8-7,1 | 5,7-6,7 | < 5,7 | Carta del pH ER, strato 0-30 cm |
| Ca scambiabile (cmol+/kg) | 30-60 | 15-30 o > 60 | < 15 | assente | non disponibile -> campo/lab o escluso |
| CaCO3 (%) | > 5 | 1-5 | < 1 | assente | carta dei suoli ER **[da verificare se c'è come attributo/layer]** |
| C/N | vedi nota | | | | non disponibile -> escluso |
| Tessitura | franco-argillosa, franca, franco-sabbioso-argillosa, argillo-limosa, franco-argillo-limosa | argillosa | franco-sabbiosa, sabbio-argillosa, franco-limosa | sabbiosa, sabbioso-franca, limosa | carta dei suoli ER |
| Quota (m slm) | < 600 | 600-1000 | 1000-1600 | > 1600 | DTM ER |
| Tipo di bosco | latifoglie fresche | misti freschi | umidi | altri | Carta forestale ER, traduzione sui tipi forestali ER da fare |
| Struttura bosco | copertura aperta, radure, sentieri | copertura moderata | chiusa con qualche arbusto | chiusa con sottobosco fitto | **solo campo** |
| Piante ospiti | > 2 specie nello strato arboreo + nocciolo | ≥ 1 arborea + ≥ 1 nel piano inferiore | ≥ 1 specie | nessuna | Carta forestale (parziale) + campo |
| Orchidee (Cephalanthera, Epipactis, Cypripedium) | > 1 specie | 1 specie | | nessuna | **solo campo** |
| Insetti (Leiodes, Bolbelasmus unicornis, Odonteus armiger, mosche Suillia) | +3 se presente almeno uno | | | | **solo campo** |

Nota C/N: la tabella del paper dà 3 punti a C/N > 15, ma nelle tabelle dei risultati gli stessi autori danno 3 punti a valori 10-15, 2 punti a 15-20 e 1 punto sopra 20. Anche alcuni punteggi CaCO3 non seguono le soglie. Usare la tabella come guida, non come verità; dato che il C/N non lo abbiamo da dati remoti, per ora si esclude.

Piante ospiti dalla lista del paper (Polonia): Betula, Carpinus betulus, Corylus avellana, Fagus, Quercus spp., Populus, Tilia, Ulmus, Abies alba, Picea abies, Pinus nigra, Pinus sylvestris. Per l'Appennino aggiungere **Ostrya carpinifolia** (carpino nero): Moser et al. 2017 (*Fungal Ecology*) caratterizzano i siti di aestivum proprio in boschi di faggio, carpino bianco e carpino nero su substrato calcareo, con indicatori di clima caldo-secco, suolo alcalino e chioma aperta. Roverella e cerro rientrano in Quercus spp.

Limite dichiarato: VTH è tarato su geologia e flora polacche e pensato per aree senza cartografia digitale. Qui la cartografia c'è, quindi lo usiamo come struttura di punteggio e non come verità.

### 4.2 La carta regionale del bianco (CAPP), come esempio di metodo GIS

Regione ER con UniBo e Arpae, note illustrative marzo 2026; articolo Laruccia et al., *Italian Journal of Mycology* 2020, 49, 38-53. È per **T. magnatum**, non per il nostro target, ma il metodo è riusabile:

- indice suolo che combina CaCO3, pH 0-30 cm e tessitura;
- Topographic Position Index su raggio 250 m;
- indice di continentalità (griglia ERG5 Arpae, 5 km);
- boschi con almeno una delle due specie principali simbionte;
- esclusi: aree non boscate, oltre 975 m (soglia del bianco), pianura alluvionale;
- 5 classi di idoneità S1-N stile FAO; validazione nel parmense con DNA del micelio nel suolo.

La CAPP stessa si mostra nell'app come layer informativo separato (il bianco esce nella stessa stagione del nero di Fragno).

### 4.3 Score dell'app

- **Score remoto** (precalcolato, raster): somma dei parametri VTH disponibili da dati (roccia madre, pH, CaCO3 se c'è, tessitura, quota, tipo di bosco, ospiti parziali), normalizzata sul massimo ottenibile con quei parametri. Maschera: solo superficie boscata.
- **Score sul posto**: la checklist aggiunge struttura, ospiti osservati, orchidee, insetti. Opzionali: pH da kit da campo, test di effervescenza per i carbonati. Il risultato torna sulla scala VTH a 36 punti, con indicato quali parametri sono stimati e quali osservati.
- **Feature candidate** da testare in calibrazione, non nel punteggio iniziale: TPI 250 m, esposizione, pendenza, continentalità. Sono ipotesi, non regole.
- **Calibrazione** (fase 3): con i dati delle uscite, compresi i giri a vuoto, si rivedono pesi e soglie. Con pochi punti niente regressioni ambiziose: VTH resta il prior, si sposta solo dove i dati insistono.

## 5. Dati

CRS dei dati regionali: EPSG:5659 (Monte Mario / TM Emilia-Romagna). La pipeline riproietta in EPSG:3857 per la mappa. Licenza: open data del geoportale ER, **[da verificare per ogni dataset]** (attesa CC BY).

| Dato | Uso | Accesso | Stato |
|---|---|---|---|
| DTM 5x5 (ed. 2014) | quota, pendenza, TPI | WCS `https://servizigis.regione.emilia-romagna.it/wcs/dtm10k_ed2014`, WMS `.../wms/dtm10k_ed2014` | endpoint da metadati INSPIRE |
| DEM 10x10 (usato dalla CAPP) | alternativa più leggera | `http://geoportale.regione.emilia-romagna.it/it/download/prodottiraster` | link dalle note CAPP |
| Carta dei suoli 1:50.000 (2018, copre il 71% della regione) + 1:250.000 (tutta) | tessitura, CaCO3?, drenaggio | WMS `https://servizigis.regione.emilia-romagna.it/wms/suoli`; webgis `https://geo.regione.emilia-romagna.it/cartpedo/` | attributi esatti **[da verificare]** |
| Carta del pH dei suoli 0-30 cm | pH | note: `https://mappegis.regione.emilia-romagna.it/gstatico/documenti/dati_pedol/pH_0_30.pdf` (descrive la consultazione su MokaSuoli e sul geoportale) | download **[da verificare]** |
| Catalogo dei suoli ER | valori tipici per tipo di suolo | `https://mappegis.regione.emilia-romagna.it/gstatico/documenti/dati_pedol/Catalogo_suoli_RER.pdf` | ok |
| Carta geologica 1:50.000 | roccia madre | WMS `https://servizigis.regione.emilia-romagna.it/wms/geologia50k`; webgis `https://servizimoka.regione.emilia-romagna.it/mokaApp/applicazioni/geo` | layer litologie **[da verificare]**, esiste anche 1:10.000 |
| Carta forestale regionale 1:10.000 | tipo di bosco, specie dominanti | pagina "cartografia interattiva foreste" su `ambiente.regione.emilia-romagna.it/it/parchi-natura2000/foreste/...` | download/WMS **[da verificare]** |
| Carta della vegetazione | supporto per gli ospiti | WMS/WFS `http://servizigis.regione.emilia-romagna.it/wms/carta_della_vegetazione` | copertura probabilmente parziale **[da verificare]** |
| ERG5 Arpae (griglia 5 km) | continentalità, stress idrico | portale dati Arpae | **[da verificare]** |
| CAPP Tuber magnatum | layer informativo | webgis `https://agri.regione.emilia-romagna.it/MotoreGis/TemiAgricoli/gis.html` (risoluzione ridotta) | download/WMS **non trovato**: chiedere alla Regione |
| Basemap | sfondo offline | estratto Protomaps PMTiles dell'area, online anche CTR 1:25.000 light via WMS `.../wms/dbtr_ctr25_light` | ok |

Area di partenza: provincia di Parma, fascia collinare e montana boscata (Val Baganza, Val Parma, Val Taro), poi il resto della regione se ha senso.

Risoluzione di output: i suoli sono al 50.000, quindi uno score a 5 m sarebbe precisione finta. Partire da 20-25 m, il DTM a 5 m serve solo per derivare quota e morfologia.

## 6. Architettura

```
pipeline/            Python: GDAL, rasterio, geopandas
  fetch/             scarico WMS/WCS/zip, cache locale
  derive/            pH, tessitura, roccia->punti, quota->punti, maschera bosco
  score/             score remoto VTH normalizzato
  export/            GeoTIFF -> MBTiles -> PMTiles (pmtiles convert)
app/                 Vue 3 + TypeScript + Vite (stesso stack di sempre)
  map/               MapLibre GL JS + protocollo pmtiles
  field/             checklist sul posto, calcolo score VTH completo
  diary/             uscite, ritrovamenti, giri a vuoto
  rules/             calendario e regole come dati versionati
```

- PWA con service worker (vite-plugin-pwa): i PMTiles dell'area scelta si scaricano una volta e funzionano offline in bosco.
- Dati utente in IndexedDB (Dexie). Export/import in file, cifrato con passphrase via WebCrypto. Niente sync nell'MVP.
- Hosting statico; in alternativa il server di casa.
- Posizione GPS solo locale. Le coordinate dei ritrovamenti non lasciano mai il telefono se non tramite export esplicito.

## 7. Modello dati (prima bozza)

```ts
type Species = 'aestivum' | 'uncinatum' | 'magnatum' | 'borchii' | 'brumale' | 'other'

interface Spot {            // punto o poligono di interesse
  id: string
  geom: GeoJSON.Point | GeoJSON.Polygon
  remoteScore: number       // 0..1, dalla pipeline
  notes?: string
}

interface FieldAssessment { // checklist sul posto, scala VTH
  spotId: string
  date: string
  forestStructure: 0 | 1 | 2 | 3
  hosts: { species: string[]; hazelPresent: boolean; score: 0 | 1 | 2 | 3 }
  orchids: { genera: string[]; score: 0 | 2 | 3 }
  insects: boolean
  phField?: number
  carbonatesFizz?: boolean
  totalScore: number        // su 36, con elenco parametri stimati vs osservati
}

interface Outing {          // anche i giri a vuoto: sono dati
  id: string
  date: string
  track?: GeoJSON.LineString
  spotsVisited: string[]
  dog: string
  weather?: string
}

interface Find {
  outingId: string
  position: GeoJSON.Point
  species: Species
  grams?: number
  depthCm?: number
  hostNearby?: string
  photo?: Blob
}
```

## 8. Roadmap

- **Fase 0, spike (novembre 2026, un paio di serate).** Verificare tutti i **[da verificare]** del punto 5. Output: un notebook che carica pH, suoli, geologia, DTM e forestale su una sola valle (Val Baganza) e li mostra sovrapposti. Se un dato chiave non è scaricabile, fermarsi e decidere.
- **Fase 1, mappa (dicembre - gennaio).** Pipeline completa sulla provincia, score remoto, PWA con mappa offline e calendario "aperto/chiuso oggi" per specie.
- **Fase 2, campo e diario (febbraio - maggio).** Checklist VTH, diario uscite e ritrovamenti, export cifrato. Pronta prima della riapertura dell'aestivum il 1 giugno 2027.
- **Fase 3, calibrazione (dopo la stagione estiva 2027 e poi dopo l'autunno).** Confronto score vs uscite, revisione pesi, eventualmente feature morfologiche e climatiche.

## 9. Domande aperte

1. I dati chiave (pH, suoli con CaCO3, forestale) sono scaricabili come vettori/raster o solo consultabili via webgis?
2. Licenza effettiva di ciascun dataset, e della CAPP in particolare.
3. Tabella di lookup unità geologiche ER -> classi roccia madre VTH: va costruita a mano, con prudenza.
4. Traduzione dei "forest habitat types" polacchi sui tipi forestali ER.
5. Quanto pesa davvero il bosco "aperto" in Appennino rispetto ai boschi polacchi del test.
6. Se un giorno il diario diventa prodotto: pagamento una tantum, tutto locale. Nessuna mappa condivisa, mai.

## 10. Fonti

- Calendario raccolta tartufi ER 2026-2030: https://agricoltura.regione.emilia-romagna.it/tartufi/raccolta/calendari/calendario-tartufi-e-r/@@download/file
- L.R. 24/1991: https://agricoltura.regione.emilia-romagna.it/fitosanitario/normativa/regionale/legge-regionale-n.-24-del-2-settembre-1991/@@download/file
- Note illustrative CAPP Tuber magnatum (marzo 2026): https://agricoltura.regione.emilia-romagna.it/tartufi/pubblicazioni/note-illustrative-tuber-magnatum_marzo-_2026.pdf/@@download/file
- Laruccia et al. 2020, Ital. J. Mycol.: https://italianmycology.unibo.it/article/view/10832
- Rosa-Gruszecka et al. 2021, Forests (VTH): https://doi.org/10.3390/f12091239
- Moser et al. 2017, Fungal Ecology, indicatori ecologici di T. aestivum: https://muni.cz/en/research/publications/1802277
- Thomas 2013, Acta Mycologica, pH e micorrize di T. aestivum (ottimo osservato 7,51): https://doi.org/10.5586/am.2012.019
- Tabella regionale "tartufaia coltivata, raccolta riservata": https://agricoltura.regione.emilia-romagna.it/tartufi/tartuficoltura/tabelle/tabella-tartufaia-coltivata.pdf
- Metadati DTM 5x5 ER: https://inspire-geoportal.ec.europa.eu/srv/api/records/r_emiro:2016-08-08T155835

## 11. Decisioni di implementazione (19 ottobre 2026)

Prese costruendo la prima versione. Dove si discostano dal resto del brief, valgono queste finché non si decide altrimenti.

- **Modello come dati condivisi.** Parametri, soglie, classi, specie ospiti e contratto dei tile stanno in `model/vth-v1.json`, letto sia dalla pipeline sia dall'app. Cambiare una soglia = nuova versione del modello.
- **Soglie VTH come regole ordinate.** Vince la prima che corrisponde; i buchi tra gli intervalli del paper (pH 7,1-7,2, quota 1000) si chiudono con intervalli semiaperti.
- **Ospiti da remoto: massimo 1 punto.** Dalla carta forestale si vede solo lo strato arboreo, non il nocciolo, quindi da remoto vale solo la regola "≥ 1 specie". Lo score remoto si normalizza su questo massimo, come chiede §4.3.
- **Soglie minime (scelte di progetto, non del paper).** Score remoto solo con almeno 4 parametri disponibili; classe sul posto provvisoria sotto 8 parametri. Senza queste, pochi parametri al massimo davano "Alta" con 5 dati su 11.
- **Effervescenza → CaCO3.** Euristica prudente sulle classi FAO 2006 (nessuna 0, udibile 1, visibile 2, forte 3 punti). **[da verificare]** sul campo.
- **Score remoto vettoriale, non raster.** La pipeline lavora su griglia a 25 m, poi poligonizza per combinazione di punteggi e scrive un PMTiles vettoriale (layer `vth`) con i punti di ogni parametro. In app si colora per classe o per singolo parametro e si interroga in un punto, anche senza mappa a schermo.
- **Mappe come file nel telefono.** Score e basemap offline si importano come `.pmtiles` e restano in IndexedDB; si leggono a pezzi con `FileSource`. Niente range request da cachare nel service worker.
- **Traccia come punti con tempo e precisione** (`TrackPoint[]`), non `GeoJSON.LineString`: serve per la calibrazione e si converte quando occorre.
- **Spot "riservato"** per le tartufaie con tabella: è la segnalazione manuale prevista in §3.
- **Rete dall'ambiente cloud di sviluppo.** I domini `*.regione.emilia-romagna.it` sono bloccati dal proxy dell'ambiente: la Fase 0 (verifica dei dati) va fatta da un computer normale o dopo aver aggiunto quei domini alla rete dell'ambiente. Il calendario in app è trascritto da questo brief e segnato come non verificato sul PDF della delibera.
