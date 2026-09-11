# FileRenamer

Rinomina file in massa con interfaccia grafica (tkinter), estensioni sempre preservate e regole personalizzabili salvate automaticamente.

## Funzionalità

- Rinomina **qualsiasi tipo di file**, l'estensione non viene mai toccata.
- Regole modificabili dal menu `File -> Regole` (sostituzioni, separatori, maiuscole/minuscole) salvate **automaticamente** su `json/regole.json`.
- Riconosce in automatico tutte le **estensioni** dei file caricati e permette di **filtrare** la lista (una o più estensioni alla volta).
- Per ogni file puoi scegliere tramite la colonna **Azione** se rinominarlo (`Rinomina`) o escluderlo (`Escludi`): basta un **clic** sulla cella, senza menu a tendina.
- **Anteprima** dei nuovi nomi con colori: verde = il nome cambierà, grigio corsivo = invariato, grigio tenue = escluso.
- **Tema chiaro/scuro** attivabile dal pulsante in alto a destra (la scelta viene ricordata).
- Carica una cartella intera oppure **singoli file** scelti.
- Crea un **archivio .zip** con i file selezionati (rinominati), così dopo la decompressione hai la cartella pronta.
- Pulsante **Annulla** per ripristinare l'ultima rinomina.
- **Pulisci lista** svuota i file caricati e azzera anche il percorso della cartella.
- Compatibilità da riga di comando:
  ```
  python rename_file.py <cartella>
  ```

## Requisiti

- Python 3.10+ (nessuna dipendenza esterna: usa solo la libreria standard).

## Avvio

```bash
python rename_file.py
```

Oppure esegui direttamente l'eseguibile in `relases/` (Windows).

## Creare l'eseguibile (.exe)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name FileRenamer rename_file.py
```

## Struttura del progetto

```
FileRenamer/
├── rename_file.py        # applicazione completa
├── json/                 # configurazione (auto-generata)
│   ├── regole.json       # regole di rinomina
│   └── settings.json     # preferenze locali (tema chiaro/scuro)
└── relases/              # eseguibili compilati (Release)
```