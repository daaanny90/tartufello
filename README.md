# fiuto

**App:** https://daaanny90.github.io/tartufello/ (da Chrome su Android: menu → Installa app)

App personale per decidere **dove portare il cane a cercare tartufo nero** (*Tuber aestivum* / *uncinatum*) nell'Appennino parmense. Il perché, il modello e i dati sono in [`BRIEF.md`](BRIEF.md).

- [`model/vth-v1.json`](model/vth-v1.json): il modello Virtual Truffle Hunting adattato, condiviso da pipeline e app.
- [`pipeline/`](pipeline/README.md): dai dati regionali alla mappa di idoneità (`.pmtiles`).
- [`app/`](app/README.md): la PWA da usare in bosco. Calendario, mappa offline, checklist sul posto, diario, backup cifrato.

Tutto resta sul telefono: niente account, niente server, niente telemetria. Il modello restringe le zone, l'ultimo metro lo fa il cane.
