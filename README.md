# fiuto

**App:** https://daaanny90.github.io/tartufello/ (da Chrome su Android: menu → Installa app). Per il test sul campo: [`CAMPO.md`](CAMPO.md).

App personale per decidere **dove portare il cane a cercare tartufo nero** (*Tuber aestivum* / *uncinatum*) nell'Appennino parmense. Il perché, il modello e i dati sono in [`BRIEF.md`](BRIEF.md).

- [`model/vth-v2.json`](model/vth-v2.json): il modello Virtual Truffle Hunting adattato all'Appennino, condiviso da pipeline e app.
- [`pipeline/`](pipeline/README.md): dai dati regionali alla mappa di idoneità e alla mappa di base offline (`.pmtiles`).
- [`app/`](app/README.md): la PWA da usare in bosco. Calendario, mappa offline, checklist sul posto, diario, backup cifrato.

Tutto resta sul telefono: niente account, niente server, niente telemetria. Il modello restringe le zone, l'ultimo metro lo fa il cane.

## Come leggere la mappa (e quanto fidarsi)

**"Alta" non vuol dire "qui c'è il tartufo".** Vuol dire che i dati regionali (roccia madre, pH, carbonati, tessitura del suolo, quota, tipo di bosco) sono compatibili con lo scorzone secondo le soglie VTH. Sono condizioni necessarie, non sufficienti.

Perché oggi "alta" vale poco, almeno in Val Baganza:

- **La valle esce quasi tutta "alta".** È calcarea, alcalina e piena di roverella e carpino nero: un quarto del bosco con score prende il massimo, la media è 0,86. Tutto vero, ma non aiuta a scegliere.
- **Mancano dati.** La carta dei suoli copre solo il 37% del medio Appennino: sono le zone grigie, "dati insufficienti". La roccia madre è classificata solo sul 18% del bosco. Tocca un punto e guarda quanti parametri ha: un "alta" fatto con 4 parametri vale meno di uno con 6.
- **Il suolo è una media grossolana.** Ogni poligono della carta 1:50.000 prende i valori del suo suolo prevalente, ma dentro un poligono di suoli ce ne sono diversi.
- **Le classi dei boschi sono un'ipotesi nostra.** Termofile 3, mesofile 2, umidi 1, altri 0: segue Moser et al. 2017, da verificare.
- **Mancano le cose che decidono davvero**, che dai dati non si vedono: struttura del bosco, nocciolo, orchidee, esposizione, microhabitat.
- **Nessuna validazione.** VTH è stato provato su 20 siti in Polonia. Questa versione appenninica non è ancora stata confrontata con nessun ritrovamento.

Di cosa fidarsi di più:

- **Il rosso e il giallo.** La mappa è più brava a dire dove *non* andare (suoli acidi, quote alte, rimboschimenti di conifere) che dove andare.
- **La checklist sul posto.** Aggiunge proprio quello che manca alla mappa, osservato da te. Anche lei però non è validata.

Come usarla in pratica:

1. La mappa dice quali zone **non scartare**.
2. Dentro le zone "alte" scegli col sopralluogo e la checklist: bosco aperto, roverella o carpino nero con nocciolo, orchidee, versanti caldi.
3. L'ultimo metro lo fa il cane.

Diventa affidabile solo con i dati di campo, **giri a vuoto compresi**: è la calibrazione prevista dopo l'estate 2027. I sopralluoghi di quest'inverno sono i primi dati utili.

## Da dove arrivano i dati

Tutti i dati cartografici sono open data della **Regione Emilia-Romagna**, verificati il 20/10/2026. Endpoint, attributi e note di metodo stanno in [`pipeline/sources.toml`](pipeline/sources.toml) e [`pipeline/FASE0.md`](pipeline/FASE0.md); gli esiti in [`BRIEF.md`](BRIEF.md) §12.

| Dato | Cosa ne facciamo | Licenza | Note |
|---|---|---|---|
| DTM 5x5 (ed. 2025) | quota; rilievo ombreggiato e curve di livello della mappa offline | CC BY 4.0 | servizio WCS `dtm5x5` |
| Carta dei suoli 1:50.000 (ed. 2021) | pH, carbonati e tessitura 0-30 cm, ricavati dai profili misurati del suolo prevalente | CC BY 4.0 | copre il 37% del medio Appennino |
| Carta geologica 1:50.000 (unità geologiche) | roccia madre | CC BY 4.0 | classificata solo sul 18% del bosco della Val Baganza, in parte in bozza |
| Carta forestale regionale 2025 (Parma) | dove c'è bosco, tipo di bosco | CC BY 4.0 (note legali del sito) | la pagina del dato non indica una licenza propria |
| Rete escursionistica regionale | sentieri della mappa offline | CC BY 4.0 | |
| Database topografico regionale (DBTR) | strade, corsi d'acqua, località della mappa offline | CC BY 4.0 (sentieri DBTR: CC BY 3.0) | scaricato da un servizio pubblico ArcGIS: da chiedere alla Regione se è un canale ammesso |
| Calendario raccolta 2026-2030 (DGR 137/2026) | aperto/chiuso per specie, sospensioni | atto pubblico | confrontato con il PDF ufficiale |
| L.R. 24/1991, testo coordinato | orari, limite di 1 kg, cani, aree faunistiche | atto pubblico | testo non ufficiale: fa fede il Bollettino |

Ancora **non usati**: la carta raster del pH a 100 m (MinERva), i confini degli istituti faunistici e la carta del tartufo bianco (CAPP). I primi due stanno su host che l'ambiente cloud di sviluppo non raggiunge; per la CAPP non c'è un download pubblico.

Altro:

- **Modello**: Virtual Truffle Hunting, Rosa-Gruszecka, Hilszczańska, Pacioni, *Forests* 2021 (doi:10.3390/f12091239, CC BY), adattato all'Appennino con Moser et al. 2017. Le modifiche sono in `model/vth-v2.json`, alla voce `changes`.
- **Sfondo online** (solo con rete): OpenTopoMap (CC-BY-SA) e OpenStreetMap (ODbL). Vedono quale zona stai guardando; la mappa offline no.
- **Font e icone della mappa offline**: Noto Sans (SIL OFL) e sprite Protomaps derivati da tangrams/icons (MIT), in `app/public/basemap/`.

L'app mostra le attribuzioni nel pulsante (i) della mappa e in Altro.
