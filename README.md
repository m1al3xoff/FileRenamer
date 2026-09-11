# FileRenamer

Rinomina file in massa con interfaccia grafica (tkinter), estensioni sempre preservate e regole personalizzabili salvate automaticamente.

## Funzionalità

- Rinomina **qualsiasi tipo di file**, l'estensione non viene mai toccata.
- Regole modificabili dal menu `File -> Regole` (sostituzioni, separatori, maiuscole/minuscole) salvate **automaticamente** su `json/regole.json`.
- Riconosce in automatico tutte le **estensioni** dei file caricati e permette di **filtrare** la lista (una o più estensioni alla volta).
- Per ogni file puoi scegliere tramite la colonna **Azione** se rinominarlo (`Rinomina`) o escluderlo (`Escludi`).
- **Anteprima** dei nuovi nomi con colori: verde = il nome cambierà, grigio = invariato.
- Carica una cartella intera oppure **singoli file** scelti.
- Crea un **archivio .zip** con i file selezionati (rinominati), così dopo la decompressione hai la cartella pronta.
- Pulsante **Annulla** per ripristinare l'ultima rinomina.
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
├── json/                 # configurazione regole (auto-generata)
│   └── regole.json
└── relases/              # eseguibili compilati (Release)
```