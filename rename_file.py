"""
rename_file.py
===============================================================================
FileRenamer - utility per rinominare file in massa con interfaccia grafica.

Caratteristiche:
  - Regole modificabili dal menu File -> Regole, salvate automaticamente.
  - Funziona con QUALSIASI tipo di file: l'estensione viene sempre preservata.
  - Riconosce automaticamente le estensioni e permette di filtrare la lista.
  - Per ogni file puoi escluderlo (o ri-includerlo) con un semplice clic
    sulla colonna "Azione".
  - Anteprima chiara dei nuovi nomi, distinta con colori dal nome originale.
  - Carica una cartella intera oppure singoli file scelti.
  - Esporta in .zip i file selezionati (con i nomi previsti).
  - Annulla l'ultima operazione di rinomina.
  - Tema chiaro/scuro, salvato nelle impostazioni.
  - Compatibilità da riga di comando: python rename_file.py <directory>

Senza argomenti si apre l'interfaccia grafica.
"""

import json
import os
import re
import sys
import tkinter as tk
import zipfile
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk

# ============================================================================
# Configurazione
# ============================================================================

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _find_rules_file():
    search = [os.path.join(BASE_DIR, "json", "regole.json"),
              os.path.join(BASE_DIR, "regole.json")]
    if getattr(sys, "frozen", False):
        parent = os.path.dirname(BASE_DIR)
        search += [os.path.join(parent, "json", "regole.json"),
                   os.path.join(parent, "regole.json")]
    search.sort(key=lambda path: path.endswith(os.path.join("json", "regole.json")),
                reverse=True)
    for path in search:
        if os.path.isfile(path):
            return path
    return search[0]


RULES_FILE = _find_rules_file()
SETTINGS_FILE = os.path.join(os.path.dirname(RULES_FILE), "settings.json")

ZIP_FOLDER = "FileRenamer"

INVALID_CHARS = set(r'<>:"/\|?*')
CONTROL_CHARS = set(map(chr, range(32)))
RESERVED_NAMES = ({f"COM{i}" for i in range(1, 10)}
                  | {f"LPT{i}" for i in range(1, 10)}
                  | {"CON", "PRN", "AUX", "NUL"})

DEFAULT_RULES = {
    "replacements": [
        {"find": "The.Big.Bang.Theory.", "replace": ""},
        {"find": ".ITA.ENG.1080p.BluRay.x264-PiNG", "replace": ""},
        {"find": " iTA ENG 1080p BluRay x264-PiNG", "replace": ""},
        {"find": " ITA 1080p BluRay x264-PiNG", "replace": ""},
    ],
    "separators": [".", "-", "_"],
    "separator_action": "space",
    "case_mode": "none",
    "clean_invalid": True,
}

VERSION = "5.0"

# ============================================================================
# Modello dati
# ============================================================================


@dataclass
class Replacement:
    find: str
    replace: str = ""

    @classmethod
    def from_dict(cls, data):
        return cls(data.get("find", ""), data.get("replace", ""))

    def to_dict(self):
        return {"find": self.find, "replace": self.replace}


@dataclass
class Rules:
    replacements: list[Replacement] = field(default_factory=list)
    separators: list[str] = field(default_factory=list)
    separator_action: str = "space"
    case_mode: str = "none"
    clean_invalid: bool = True

    @classmethod
    def default(cls):
        return cls.from_dict(DEFAULT_RULES)

    @classmethod
    def from_dict(cls, data):
        replacements = [Replacement.from_dict(item)
                        for item in data.get("replacements", [])]
        return cls(
            replacements=replacements,
            separators=list(data.get("separators", [])),
            separator_action=data.get("separator_action", "space"),
            case_mode=data.get("case_mode", "none"),
            clean_invalid=data.get("clean_invalid", True),
        )

    def to_dict(self):
        return {
            "replacements": [item.to_dict() for item in self.replacements],
            "separators": list(self.separators),
            "separator_action": self.separator_action,
            "case_mode": self.case_mode,
            "clean_invalid": self.clean_invalid,
        }


# ============================================================================
# Persistenza delle regole e delle impostazioni
# ============================================================================


def load_rules():
    rules = Rules.default()
    if os.path.exists(RULES_FILE):
        try:
            with open(RULES_FILE, "r", encoding="utf-8") as file:
                rules = Rules.from_dict(json.load(file))
        except (OSError, ValueError):
            pass
    save_rules(rules)
    return rules


def save_rules(rules):
    directory = os.path.dirname(RULES_FILE)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(RULES_FILE, "w", encoding="utf-8") as file:
        json.dump(rules.to_dict(), file, ensure_ascii=False, indent=4)


def load_settings():
    if os.path.isfile(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except (OSError, ValueError):
            pass
    return {}


def save_settings(data):
    directory = os.path.dirname(SETTINGS_FILE)
    if directory and not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


# ============================================================================
# Motore di trasformazione del nome
# ============================================================================


def title_case(text):
    return " ".join(word[:1].upper() + word[1:].lower()
                    for word in text.split())


CASE_FUNCTIONS = {
    "lower": str.lower,
    "upper": str.upper,
    "title": title_case,
}


def clean_name(name):
    cleaned = "".join(" " if ch in INVALID_CHARS or ch in CONTROL_CHARS else ch
                      for ch in name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    if cleaned.lower() in RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned


def _apply_replacements(name, replacements):
    for item in replacements:
        if item.find:
            name = name.replace(item.find, item.replace)
    return name


def _apply_separators(name, pattern, sub):
    return re.sub(pattern, sub, name) if pattern else name


def _apply_case(name, function):
    return function(name) if function else name


def _apply_cleaning(name, clean):
    return clean_name(name) if clean else name


def build_transform(rules):
    separator_pattern = (f"[{re.escape(''.join(rules.separators))}]"
                         if rules.separators else None)
    separator_sub = " " if rules.separator_action == "space" else ""
    case_function = CASE_FUNCTIONS.get(rules.case_mode)

    def transform(name):
        name = _apply_replacements(name, rules.replacements)
        name = _apply_separators(name, separator_pattern, separator_sub)
        name = _apply_case(name, case_function)
        return _apply_cleaning(name, rules.clean_invalid)

    return transform


def compute_new_name(full_path, transform):
    base, ext = os.path.splitext(os.path.basename(full_path))
    return f"{transform(base) or base}{ext}"


def file_extension(filename):
    return os.path.splitext(filename)[1].lower()


# ============================================================================
# Funzionamento da riga di comando
# ============================================================================


def rename_files_in_directory(directory):
    rules = load_rules()
    transform = build_transform(rules)
    renamed = 0
    for filename in sorted(os.listdir(directory)):
        full_path = os.path.join(directory, filename)
        if not os.path.isfile(full_path):
            continue
        new_name = compute_new_name(full_path, transform)
        if new_name == filename:
            continue
        try:
            os.rename(full_path, os.path.join(directory, new_name))
            print(f"Rinominato: {filename} -> {new_name}")
            renamed += 1
        except OSError as error:
            print(f"Errore su '{filename}': {error}")
    print(f"Fatto. File rinominati: {renamed}")


# ============================================================================
# Tema (chiaro / scuro)
# ============================================================================

THEMES = {
    "light": {
        "bg": "#eef2f7",
        "panel": "#ffffff",
        "accent": "#1e3a8a",
        "accent_bright": "#2563eb",
        "accent_bright_hover": "#1d4ed8",
        "accent_text": "#cbd5e1",
        "text": "#111827",
        "muted": "#64748b",
        "ok": "#047857",
        "row_changed": "#e6f7ec",
        "row_excluded": "#f3f4f6",
        "row_selected": "#dbeafe",
        "tree_bg": "#ffffff",
        "tree_heading": "#f1f5f9",
        "heading_active": "#e2e8f0",
        "button_active": "#dbeafe",
        "button_disabled": "#e5e7eb",
        "field": "#ffffff",
        "border": "#cbd5e1",
        "title_bg": "#1e3a8a",
        "title_fg": "#ffffff",
    },
    "dark": {
        "bg": "#0f172a",
        "panel": "#1e293b",
        "accent": "#0b1220",
        "accent_bright": "#3b82f6",
        "accent_bright_hover": "#2563eb",
        "accent_text": "#94a3b8",
        "text": "#e2e8f0",
        "muted": "#94a3b8",
        "ok": "#34d399",
        "row_changed": "#0c2f22",
        "row_excluded": "#16213a",
        "row_selected": "#1d4ed8",
        "tree_bg": "#0f172a",
        "tree_heading": "#1e293b",
        "heading_active": "#334155",
        "button_active": "#334155",
        "button_disabled": "#293548",
        "field": "#0f172a",
        "border": "#334155",
        "title_bg": "#0b1220",
        "title_fg": "#ffffff",
    },
}

THEME = dict(THEMES["light"])


def apply_theme(root, dark=False):
    global THEME
    THEME = dict(THEMES["dark" if dark else "light"])
    palette = THEME
    root.configure(bg=palette["bg"])

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    style.configure("TFrame", background=palette["bg"])
    style.configure("TLabelframe", background=palette["bg"],
                    bordercolor=palette["border"])
    style.configure("TLabelframe.Label", background=palette["bg"],
                    foreground=palette["text"], font=("Segoe UI", 9, "bold"))
    style.configure("TLabel", background=palette["bg"],
                    foreground=palette["text"])
    style.configure("TCheckbutton", background=palette["bg"],
                    foreground=palette["text"])
    style.configure("TRadiobutton", background=palette["bg"],
                    foreground=palette["text"])

    style.configure("TButton", background=palette["panel"],
                    foreground=palette["text"], borderwidth=1,
                    padding=(10, 6), font=("Segoe UI", 10))
    style.map("TButton",
              background=[("active", palette["button_active"]),
                          ("disabled", palette["button_disabled"])])
    style.configure("Primary.TButton", background=palette["accent_bright"],
                    foreground="#ffffff", borderwidth=0, padding=(14, 8),
                    font=("Segoe UI", 10, "bold"))
    style.map("Primary.TButton",
              background=[("active", palette["accent_bright_hover"]),
                          ("disabled", palette["button_disabled"])])

    style.configure("TEntry", fieldbackground=palette["field"],
                    foreground=palette["text"], bordercolor=palette["border"],
                    padding=4)
    style.configure("TCombobox", fieldbackground=palette["field"],
                    foreground=palette["text"], padding=2)

    style.configure("Treeview", background=palette["tree_bg"],
                    fieldbackground=palette["tree_bg"],
                    foreground=palette["text"], rowheight=28,
                    bordercolor=palette["border"], font=("Segoe UI", 10))
    style.map("Treeview",
              background=[("selected", palette["row_selected"])],
              foreground=[("selected", palette["text"])])
    style.configure("Treeview.Heading", background=palette["tree_heading"],
                    foreground=palette["text"], padding=7,
                    font=("Segoe UI", 10, "bold"))
    style.map("Treeview.Heading",
              background=[("active", palette["heading_active"])])

    style.configure("Status.TLabel", background=palette["panel"],
                    foreground=palette["text"], relief="sunken",
                    font=("Segoe UI", 9))
    style.configure("Muted.TLabel", background=palette["bg"],
                    foreground=palette["muted"], font=("Segoe UI", 9))
    return style


def style_dialog(dialog):
    dialog.configure(bg=THEME["bg"])


# ============================================================================
# Interfaccia grafica
# ============================================================================

ACTION_RENAME = "Rinomina"
ACTION_SKIP = "Escludi"


class RulesEditor(tk.Toplevel):
    SEPARATOR_OPTIONS = [".", "-", "_", " ", "+", ",", ";", "~"]
    CASE_OPTIONS = [
        ("none", "Nessuna"),
        ("lower", "Tutto minuscolo"),
        ("upper", "Tutto MAIUSCOLO"),
        ("title", "Title Case (Iniziali Maiuscole)"),
    ]
    ACTION_OPTIONS = [("space", "Sostituisci con spazio"), ("remove", "Rimuovi")]

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.rules = load_rules()
        self.title("Regole di rinomina")
        self.geometry("820x640")
        style_dialog(self)
        self.transient(app.root)
        self.grab_set()
        self._build_widgets()
        self._sync_widgets()
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build_widgets(self):
        ttk.Label(self, text="Regole di sostituzione (in ordine):").pack(
            anchor="w", padx=10, pady=(10, 2))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10)
        self.tree = ttk.Treeview(frame, columns=("find", "replace"),
                                 show="headings")
        self.tree.heading("find", text="Da trovare")
        self.tree.heading("replace", text="Sostituisci con")
        self.tree.column("find", width=360, anchor="w")
        self.tree.column("replace", width=360, anchor="w")
        scrollbar = ttk.Scrollbar(frame, orient="vertical",
                                  command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=10, pady=4)
        ttk.Button(buttons, text="Aggiungi",
                   command=self._add).pack(side="left", padx=2)
        ttk.Button(buttons, text="Modifica",
                   command=self._edit).pack(side="left", padx=2)
        ttk.Button(buttons, text="Elimina",
                   command=self._delete).pack(side="left", padx=2)
        ttk.Button(buttons, text="Su",
                   command=lambda: self._move(-1)).pack(side="left", padx=2)
        ttk.Button(buttons, text="Giù",
                   command=lambda: self._move(1)).pack(side="left", padx=2)
        ttk.Button(buttons, text="Ripristina predefinite",
                   command=self._reset).pack(side="right", padx=2)

        separators = ttk.LabelFrame(self, text="Separatori da convertire")
        separators.pack(fill="x", padx=10, pady=(6, 2))
        self.sep_vars = {}
        line = ttk.Frame(separators)
        line.pack(fill="x", padx=8, pady=4)
        for char in self.SEPARATOR_OPTIONS:
            label = "." if char == " " else char
            var = tk.BooleanVar()
            self.sep_vars[char] = var
            ttk.Checkbutton(line, text=f"'{label}'", variable=var,
                            command=self._persist).pack(side="left", padx=4)
        extra_line = ttk.Frame(separators)
        extra_line.pack(fill="x", padx=8, pady=(0, 4))
        ttk.Label(extra_line, text="Altri caratteri:").pack(side="left")
        self.extra_var = tk.StringVar()
        ttk.Entry(extra_line, textvariable=self.extra_var, width=14).pack(
            side="left", padx=6)
        self.action_var = tk.StringVar()
        for value, text in self.ACTION_OPTIONS:
            ttk.Radiobutton(extra_line, text=text, variable=self.action_var,
                            value=value, command=self._persist).pack(
                side="left", padx=6)

        case_frame = ttk.LabelFrame(self, text="Conversione del caso")
        case_frame.pack(fill="x", padx=10, pady=(4, 2))
        self.case_var = tk.StringVar()
        for value, text in self.CASE_OPTIONS:
            ttk.Radiobutton(case_frame, text=text, variable=self.case_var,
                            value=value, command=self._persist).pack(
                side="left", padx=8, pady=4)

        self.clean_var = tk.BooleanVar()
        ttk.Checkbutton(self,
                        text="Rimuovi caratteri non validi per Windows "
                             "(/ \\ : * ? \" < > |, spazi doppi)",
                        variable=self.clean_var,
                        command=self._persist).pack(anchor="w", padx=10,
                                                    pady=(4, 2))

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=8)
        ttk.Button(bottom, text="Chiudi", command=self.close).pack(side="right")
        ttk.Label(bottom, text="Le regole vengono salvate automaticamente.",
                  style="Muted.TLabel").pack(side="left")

    def _sync_widgets(self):
        for char, var in self.sep_vars.items():
            var.set(char in self.rules.separators)
        known = "".join(self.rules.separators)
        extra = "".join(char for char in known if char not in self.sep_vars)
        self.extra_var.set(extra)
        self.action_var.set(self.rules.separator_action)
        self.case_var.set(self.rules.case_mode)
        self.clean_var.set(self.rules.clean_invalid)
        self.refresh_tree()

    def refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.rules.replacements:
            self.tree.insert("", "end", values=(item.find, item.replace))

    def _collect(self):
        separators = [char for char, var in self.sep_vars.items() if var.get()]
        extra = "".join(dict.fromkeys(self.extra_var.get()))
        self.rules.separators = (separators
                                 + [char for char in extra
                                    if char not in separators])
        self.rules.separator_action = self.action_var.get()
        self.rules.case_mode = self.case_var.get()
        self.rules.clean_invalid = bool(self.clean_var.get())

    def _persist(self):
        self._collect()
        save_rules(self.rules)
        self.app.rules_changed()

    def _selected_index(self):
        selected = self.tree.selection()
        return int(self.tree.index(selected[0])) if selected else None

    def _add(self):
        value = self._ask_rule("Nuova regola")
        if value:
            find, replace = value
            if find:
                self.rules.replacements.append(Replacement(find, replace))
                self.refresh_tree()
                self._persist()

    def _edit(self):
        index = self._selected_index()
        if index is None:
            return
        current = self.rules.replacements[index]
        value = self._ask_rule("Modifica regola",
                               find=current.find, replace=current.replace)
        if value:
            find, replace = value
            if find:
                self.rules.replacements[index] = Replacement(find, replace)
                self.refresh_tree()
                self._persist()

    def _delete(self):
        indices = sorted((int(self.tree.index(i))
                          for i in self.tree.selection()), reverse=True)
        for index in indices:
            if 0 <= index < len(self.rules.replacements):
                del self.rules.replacements[index]
        self.refresh_tree()
        self._persist()

    def _move(self, delta):
        index = self._selected_index()
        if index is None:
            return
        new_index = index + delta
        if 0 <= new_index < len(self.rules.replacements):
            items = self.rules.replacements
            items[index], items[new_index] = items[new_index], items[index]
            self.refresh_tree()
            self._persist()

    def _reset(self):
        self.rules = Rules.default()
        self._sync_widgets()
        self._persist()

    def add_rule(self, find, replace):
        self.rules.replacements.append(Replacement(find, replace))
        self.refresh_tree()
        self._persist()

    def reload_from_file(self):
        self.rules = load_rules()
        self._sync_widgets()

    def _ask_rule(self, title, find="", replace=""):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.resizable(False, False)
        style_dialog(dialog)
        ttk.Label(dialog, text="Da trovare:").grid(row=0, column=0, sticky="w",
                                                   padx=8, pady=(8, 2))
        source = ttk.Entry(dialog, width=42)
        source.insert(0, find)
        source.grid(row=0, column=1, padx=8, pady=(8, 2))
        ttk.Label(dialog, text="Sostituisci con:").grid(row=1, column=0,
                                                        sticky="w", padx=8)
        target = ttk.Entry(dialog, width=42)
        target.insert(0, replace)
        target.grid(row=1, column=1, padx=8)
        result = {}

        def submit():
            result["value"] = (source.get(), target.get())
            dialog.destroy()

        def cancel():
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=2, column=0, columnspan=2, pady=8)
        ttk.Button(buttons, text="OK", width=10, style="Primary.TButton",
                   command=submit).pack(side="left", padx=8)
        ttk.Button(buttons, text="Annulla", width=10, command=cancel).pack(
            side="left")
        dialog.bind("<Return>", lambda e: submit())
        dialog.bind("<Escape>", lambda e: cancel())
        dialog.wait_window()
        return result.get("value")

    def close(self):
        if self.app.rules_editor is self:
            self.app.rules_editor = None
        self.destroy()


class RenameApp:
    COLUMN_ORIGINAL = "#1"
    COLUMN_PREVIEW = "#2"
    COLUMN_ACTION = "#3"

    def __init__(self, root):
        self.root = root
        self.rules_editor = None
        self.rules = load_rules()
        self.transform = build_transform(self.rules)
        self.file_items = {}
        self.visible_ids = []
        self.undo_stack = []
        self.directory = None
        self.status = tk.StringVar(value="Pronto.")
        self.dark = bool(load_settings().get("dark", False))
        apply_theme(root, self.dark)

        root.title(f"FileRenamer v{VERSION} - {RULES_FILE}")
        root.geometry("1240x740")
        root.minsize(1040, 660)

        self._build_header()
        self._build_toolbar()
        self._build_filter_bar()
        self._build_table()
        self._build_legend()
        self._build_actions()
        self._build_statusbar()
        self._build_menu()

    # ---------- header ----------
    def _build_header(self):
        self.header = tk.Frame(self.root)
        self.header.pack(fill="x")
        self.title_label = tk.Label(self.header, text="FileRenamer",
                                    font=("Segoe UI", 20, "bold"))
        self.title_label.pack(side="left", padx=(16, 6), pady=(10, 10))
        self.subtitle_label = tk.Label(self.header,
                                       text=f"Rinomina, escludi e organizza "
                                            f"i tuoi file  ·  v{VERSION}",
                                       font=("Segoe UI", 10))
        self.subtitle_label.pack(side="left", pady=(10, 10))
        self.theme_button = tk.Button(
            self.header, text="", relief="flat", bd=0, padx=12, pady=4,
            font=("Segoe UI", 10), command=self.toggle_theme)
        self.theme_button.pack(side="right", padx=12, pady=(8, 8))
        self._apply_header_theme()

    def _apply_header_theme(self):
        self.header.configure(bg=THEME["title_bg"])
        self.title_label.configure(bg=THEME["title_bg"],
                                   fg=THEME["title_fg"])
        self.subtitle_label.configure(bg=THEME["title_bg"],
                                      fg=THEME["accent_text"])
        self.theme_button.configure(
            text="Tema chiaro" if self.dark else "Tema scuro",
            bg=THEME["accent_bright"], fg="#ffffff",
            activebackground=THEME["accent_bright_hover"], activeforeground="#ffffff")

    def toggle_theme(self):
        self.dark = not self.dark
        save_settings({"dark": self.dark})
        apply_theme(self.root, self.dark)
        self._apply_header_theme()
        self._apply_tree_tags()
        self._update_status()

    def _build_menu(self):
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="Apri cartella...", command=self.browse_folder)
        file_menu.add_command(label="Carica file...", command=self.load_files)
        file_menu.add_command(label="Pulisci lista", command=self.clear_files)
        file_menu.add_separator()
        file_menu.add_command(label="Crea archivio ZIP...", command=self.export_zip)
        file_menu.add_separator()
        file_menu.add_command(label="Regole...", command=self.open_rules)
        file_menu.add_separator()
        file_menu.add_command(label="Esci", command=self.root.destroy)
        menubar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(label="Informazioni", command=self.show_about)
        menubar.add_cascade(label="Aiuto", menu=help_menu)
        self.root.config(menu=menubar)

    def _build_toolbar(self):
        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=10, pady=(10, 2))
        ttk.Label(bar, text="Cartella:").pack(side="left")
        self.folder_var = tk.StringVar()
        ttk.Entry(bar, textvariable=self.folder_var,
                  width=70).pack(side="left", padx=6)
        ttk.Button(bar, text="Sfoglia cartella...",
                   command=self.browse_folder).pack(side="left", padx=2)
        ttk.Button(bar, text="Carica file...",
                   command=self.load_files).pack(side="left", padx=6)
        ttk.Button(bar, text="Pulisci lista",
                   command=self.clear_files).pack(side="left", padx=2)

    def _build_filter_bar(self):
        frame = ttk.LabelFrame(self.root, text="Filtra per estensione")
        frame.pack(fill="x", padx=10, pady=(4, 2))
        controls = ttk.Frame(frame)
        controls.pack(fill="x", padx=8, pady=2)
        ttk.Button(controls, text="Tutti",
                   command=self.filter_all).pack(side="left", padx=2)
        ttk.Button(controls, text="Nessuno",
                   command=self.filter_none).pack(side="left", padx=2)
        self.filter_line = ttk.Frame(frame)
        self.filter_line.pack(fill="x", padx=8, pady=(0, 4))
        self.filter_vars = {}

    def _build_table(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="both", expand=True, padx=10, pady=2)
        self.tree = ttk.Treeview(frame,
                                 columns=("original", "preview", "action"),
                                 show="headings", selectmode="extended")
        self.tree.heading("original", text="Nome originale")
        self.tree.heading("preview", text="Anteprima nuovo nome")
        self.tree.heading("action", text="Azione (clic per cambiare)")
        self.tree.column("original", width=460, anchor="w")
        self.tree.column("preview", width=460, anchor="w")
        self.tree.column("action", width=150, anchor="center")
        vertical = ttk.Scrollbar(frame, orient="vertical",
                                 command=self.tree.yview)
        horizontal = ttk.Scrollbar(frame, orient="horizontal",
                                   command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set,
                            xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tree.bind("<Button-1>", self._on_tree_click)
        self._apply_tree_tags()

    def _apply_tree_tags(self):
        self.tree.tag_configure("changed", background=THEME["row_changed"],
                                foreground=THEME["ok"])
        self.tree.tag_configure("same", background=THEME["tree_bg"],
                                foreground=THEME["muted"],
                                font=("Segoe UI", 10, "italic"))
        self.tree.tag_configure("excluded", background=THEME["row_excluded"],
                                foreground=THEME["muted"])

    def _build_legend(self):
        legend = ttk.Label(
            self.root,
            text="  verde = il nome cambierà   ·   grigio corsivo = invariato   "
                 "·   grigio tenue = escluso dalla rinomina   ·   "
                 "clicca su 'Azione' per escludere o ri-includere",
            style="Muted.TLabel")
        legend.pack(fill="x", padx=12, pady=(0, 2))

    def _build_actions(self):
        utilities = ttk.Frame(self.root)
        utilities.pack(fill="x", padx=10, pady=(4, 0))
        ttk.Button(utilities, text="Anteprima",
                   command=self.refresh_preview).pack(side="left", padx=2)
        ttk.Button(utilities, text="Seleziona tutto",
                   command=self.select_all).pack(side="left", padx=2)
        ttk.Button(utilities, text="Nessuna selezione",
                   command=self.select_none).pack(side="left", padx=2)
        ttk.Button(utilities, text="Regola dal file selezionato",
                   command=self.add_rule_from_file).pack(side="left", padx=2)
        ttk.Button(utilities, text="Regole...",
                   command=self.open_rules).pack(side="right", padx=2)
        ttk.Button(utilities, text="Annulla ultima",
                   command=self.undo_last).pack(side="right", padx=2)

        main_actions = ttk.Frame(self.root)
        main_actions.pack(fill="x", padx=10, pady=(4, 8))
        ttk.Button(main_actions, text="Rinomina selezionati",
                   style="Primary.TButton",
                   command=self.apply_selected).pack(side="right", padx=4)
        ttk.Button(main_actions, text="Rinomina tutti",
                   style="Primary.TButton",
                   command=lambda: (self.select_all(),
                                    self.apply_selected())).pack(
            side="right", padx=4)
        ttk.Button(main_actions, text="Crea archivio ZIP...",
                   style="Primary.TButton",
                   command=self.export_zip).pack(side="right", padx=4)

    def _build_statusbar(self):
        frame = ttk.Frame(self.root)
        frame.pack(fill="x", side="bottom")
        ttk.Label(frame, textvariable=self.status,
                  style="Status.TLabel", anchor="w").pack(fill="x")

    # ---------- caricamento ----------
    def browse_folder(self):
        folder = filedialog.askdirectory(title="Seleziona la cartella")
        if folder:
            self.folder_var.set(folder)
            self.load_folder()

    def load_files(self, paths=None):
        if paths is None:
            paths = filedialog.askopenfilenames(
                title="Carica file",
                filetypes=[("Tutti i file", "*.*")])
        if not paths:
            return
        existing = {os.path.normcase(item["path"])
                    for item in self.file_items.values()}
        added = 0
        for path in paths:
            if os.path.normcase(path) in existing:
                continue
            filename = os.path.basename(path)
            item_id = str(len(self.file_items))
            self.file_items[item_id] = {
                "id": item_id, "path": path, "name": filename,
                "new_name": filename, "action": ACTION_RENAME,
            }
            added += 1
        if added:
            self.directory = None
            self._rebuild_filter()
            self.refresh_preview()

    def load_folder(self, path=None):
        folder = path or self.folder_var.get()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("FileRenamer",
                                 f"La cartella non esiste:\n{folder}")
            return
        self.directory = os.path.normpath(folder)
        self.folder_var.set(self.directory)
        self.file_items.clear()
        names = sorted(name for name in os.listdir(self.directory)
                       if os.path.isfile(os.path.join(self.directory, name)))
        for index, filename in enumerate(names):
            item_id = str(index)
            self.file_items[item_id] = {
                "id": item_id,
                "path": os.path.join(self.directory, filename),
                "name": filename, "new_name": filename,
                "action": ACTION_RENAME,
            }
        self._rebuild_filter()
        self.refresh_preview()

    def clear_files(self):
        self.file_items.clear()
        self.visible_ids = []
        self.directory = None
        self.folder_var.set("")
        self.filter_vars.clear()
        for child in self.filter_line.winfo_children():
            child.destroy()
        self.tree.delete(*self.tree.get_children())
        self.undo_stack.clear()
        self.status.set("Lista svuotata.")

    # ---------- filtri per estensione ----------
    def _detect_extensions(self):
        counts = {}
        for item in self.file_items.values():
            ext = file_extension(item["name"]) or "(senza estensione)"
            counts[ext] = counts.get(ext, 0) + 1
        return sorted(counts.items())

    def _rebuild_filter(self):
        for child in self.filter_line.winfo_children():
            child.destroy()
        self.filter_vars = {}
        for ext, count in self._detect_extensions():
            var = tk.BooleanVar(value=True)
            self.filter_vars[ext] = var
            ttk.Checkbutton(self.filter_line, text=f"{ext}   [{count}]",
                            variable=var, command=self.update_filter).pack(
                side="left", padx=6)
        self.update_filter()

    def filter_all(self):
        self._set_filter(True)

    def filter_none(self):
        self._set_filter(False)

    def _set_filter(self, value):
        for var in self.filter_vars.values():
            var.set(value)
        self.tree.selection_remove(*self.tree.selection())
        self.update_filter()

    def update_filter(self):
        active = {ext for ext, var in self.filter_vars.items() if var.get()}
        self.visible_ids = [
            item_id for item_id, item in self.file_items.items()
            if (file_extension(item["name"]) or "(senza estensione)") in active
            or not active
        ]
        self.tree.selection_remove(*self.tree.selection())
        self._rebuild_tree()
        self._update_status()

    # ---------- tabella ----------
    def _row_data(self, item):
        preview = item["name"] if item["action"] == ACTION_SKIP \
            else item["new_name"]
        if item["action"] == ACTION_SKIP:
            tag = "excluded"
        elif item["name"] != item["new_name"]:
            tag = "changed"
        else:
            tag = "same"
        return preview, tag

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        for item_id in self.visible_ids:
            item = self.file_items[item_id]
            preview, tag = self._row_data(item)
            self.tree.insert("", "end", iid=item_id,
                             values=(item["name"], preview, item["action"]),
                             tags=(tag,))

    def _refresh_item(self, item):
        preview, tag = self._row_data(item)
        self.tree.set(item["id"], "preview", preview)
        self.tree.set(item["id"], "action", item["action"])
        self.tree.item(item["id"], tags=(tag,))

    def _on_tree_click(self, event):
        column = self.tree.identify_column(event.x)
        item_id = self.tree.identify_row(event.y)
        if column == self.COLUMN_ACTION and item_id in self.file_items:
            self._toggle_action(item_id)

    def _toggle_action(self, item_id):
        item = self.file_items[item_id]
        item["action"] = (ACTION_SKIP if item["action"] == ACTION_RENAME
                          else ACTION_RENAME)
        self._refresh_item(item)
        self._update_status()

    def refresh_preview(self):
        for item in self.file_items.values():
            item["new_name"] = compute_new_name(item["path"], self.transform)
        self._rebuild_tree()
        self._update_status()

    def _update_status(self):
        total = len(self.file_items)
        visible = len(self.visible_ids)
        excluded = sum(1 for item in self.file_items.values()
                       if item["action"] == ACTION_SKIP)
        source = (f"cartella: {self.directory}" if self.directory
                  else "file singoli")
        self.status.set(f"File: {total}  |  Visibili: {visible}  |  "
                        f"Esclusi: {excluded}  |  {source}")

    def select_all(self):
        self.tree.selection_add(*self.tree.get_children())

    def select_none(self):
        self.tree.selection_remove(*self.tree.get_children())

    # ---------- rinomina ----------
    def apply_selected(self):
        selection = self.tree.selection()
        targets = [self.file_items[iid] for iid in selection
                   if self.file_items[iid]["action"] == ACTION_RENAME]
        excluded = [iid for iid in selection
                    if self.file_items[iid]["action"] == ACTION_SKIP]
        if not targets:
            messagebox.showinfo(
                "FileRenamer",
                "Nessun file da rinominare: seleziona dei file con azione "
                "'Rinomina' (clic sulla colonna Azione per cambiarla).")
            return
        changed = []
        unchanged = 0
        errors = []
        for item in targets:
            old_path = item["path"]
            new_name = item["new_name"]
            if new_name == item["name"]:
                unchanged += 1
                continue
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            try:
                os.rename(old_path, new_path)
                changed.append((old_path, new_path))
                item["path"] = new_path
                item["name"] = new_name
            except OSError as error:
                errors.append(f"{os.path.basename(old_path)}: {error}")
        if changed:
            self.undo_stack.append(changed)
        for item in targets:
            self._refresh_item(item)
        self.status.set(
            f"Rinominati: {len(changed)}, già uguali: {unchanged}, "
            f"esclusi: {len(excluded)}, errori: {len(errors)}, "
            f"undo disponibili: {len(self.undo_stack)}")
        if errors:
            messagebox.showwarning(
                "FileRenamer",
                "Alcuni file NON sono stati rinominati:\n\n"
                + "\n".join(errors))

    def undo_last(self):
        if not self.undo_stack:
            messagebox.showinfo("Annulla",
                                "Non ci sono operazioni da annullare.")
            return
        batch = self.undo_stack.pop()
        errors = []
        restored_map = {}
        for old_path, new_path in reversed(batch):
            try:
                if os.path.exists(new_path):
                    os.rename(new_path, old_path)
                restored_map[os.path.normcase(new_path)] = old_path
            except OSError as error:
                errors.append(f"{os.path.basename(new_path)}: {error}")
        for item in self.file_items.values():
            old_path = restored_map.get(os.path.normcase(item["path"]))
            if old_path:
                item["path"] = old_path
                item["name"] = os.path.basename(old_path)
        self.refresh_preview()
        restored = len(batch) - len(errors)
        self.status.set(
            f"Annullate: {restored} rinomine, errori: {len(errors)}, "
            f"undo rimasti: {len(self.undo_stack)}")
        if errors:
            messagebox.showwarning(
                "Annulla",
                "Alcuni ripristini non sono riusciti:\n\n"
                + "\n".join(errors))

    # ---------- esportazione ZIP ----------
    def export_zip(self):
        selection = self.tree.selection()
        item_ids = list(selection) if selection else self.visible_ids
        items = [self.file_items[iid] for iid in item_ids]
        if not items:
            messagebox.showinfo("FileRenamer",
                                "Non ci sono file da esportare.")
            return
        output = filedialog.asksaveasfilename(
            title="Salva archivio ZIP",
            defaultextension=".zip",
            filetypes=[("Archivio ZIP", "*.zip")])
        if not output:
            return
        used = {}
        try:
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in items:
                    name = (item["new_name"] if item["action"] == ACTION_RENAME
                            else item["name"])
                    name = self._unique_zip_name(name, used)
                    archive.write(item["path"], os.path.join(ZIP_FOLDER, name))
        except OSError as error:
            messagebox.showerror("FileRenamer",
                                 f"Impossibile creare l'archivio:\n{error}")
            return
        messagebox.showinfo(
            "FileRenamer",
            f"Archivio creato:\n{output}\n\n{len(items)} file salvati "
            f"nella cartella '{ZIP_FOLDER}' (li ritrovi dopo la "
            f"decompressione).")

    def _unique_zip_name(self, name, used):
        base, ext = os.path.splitext(name)
        candidate = name
        index = 1
        while candidate.lower() in used:
            candidate = f"{base} ({index}){ext}"
            index += 1
        used[candidate.lower()] = True
        return candidate

    # ---------- regole ----------
    def open_rules(self):
        if self.rules_editor:
            self.rules_editor.lift()
            return
        self.rules_editor = RulesEditor(self)

    def rules_changed(self):
        self.rules = load_rules()
        self.transform = build_transform(self.rules)
        self.refresh_preview()
        self.status.set(f"Regole aggiornate e salvate: {RULES_FILE}")

    def add_rule_from_file(self):
        selected = [self.file_items[item_id]["name"]
                    for item_id in self.tree.selection()
                    if item_id in self.file_items]
        if not selected:
            messagebox.showinfo(
                "FileRenamer",
                "Seleziona un file nella tabella per creare una regola "
                "dalla sua parte di nome.")
            return
        value = self._ask_rule_from_file(selected[0])
        if value:
            find, replace = value
            if find:
                rules = load_rules()
                rules.replacements.append(Replacement(find, replace))
                save_rules(rules)
                if self.rules_editor:
                    self.rules_editor.reload_from_file()
                self.rules_changed()

    def _ask_rule_from_file(self, filename):
        dialog = tk.Toplevel(self.root)
        dialog.title("Aggiungi regola dal file")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        style_dialog(dialog)
        ttk.Label(dialog, text="Seleziona con il mouse la parte "
                               "da trasformare:").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(8, 2))
        source = ttk.Entry(dialog, width=62)
        source.insert(0, filename)
        source.grid(row=1, column=0, columnspan=2, padx=8)
        ttk.Label(dialog, text="Sostituisci con:").grid(
            row=2, column=0, sticky="w", padx=8, pady=(8, 2))
        target = ttk.Entry(dialog, width=62)
        target.grid(row=2, column=1, sticky="ew", padx=0, pady=(8, 2))
        result = {}

        def submit():
            try:
                find = source.selection_get()
            except tk.TclError:
                find = source.get()
            result["value"] = (find, target.get())
            dialog.destroy()

        def cancel():
            dialog.destroy()

        buttons = ttk.Frame(dialog)
        buttons.grid(row=3, column=0, columnspan=2, pady=8)
        ttk.Button(buttons, text="OK", width=10, style="Primary.TButton",
                   command=submit).pack(side="left", padx=8)
        ttk.Button(buttons, text="Annulla", width=10, command=cancel).pack(
            side="left")
        dialog.bind("<Return>", lambda e: submit())
        dialog.bind("<Escape>", lambda e: cancel())
        dialog.wait_window()
        return result.get("value")

    # ---------- informazioni ----------
    def show_about(self):
        messagebox.showinfo(
            "Informazioni",
            f"FileRenamer v{VERSION}\n\n"
            "Rinomina qualsiasi file preservando l'estensione.\n"
            "Le regole (sostituzioni, separatori, caso) si modificano\n"
            "nel menu File -> Regole e vengono salvate automaticamente.\n\n"
            "Consigli rapidi:\n"
            "  - Clic sulla colonna 'Azione' per escludere o ri-includere\n"
            "  - Filtra i file per estensione dalla barra apposita\n"
            "  - 'Crea archivio ZIP' esporta i file con i nomi nuovi\n"
            "  - Il tema scuro/chiaro è nel pulsante in alto a destra\n\n"
            "Uso da riga di comando:\n"
            "  python rename_file.py <cartella>")


# ============================================================================
# Avvio
# ============================================================================


def main():
    if len(sys.argv) == 2:
        directory = sys.argv[1]
        if not os.path.isdir(directory):
            print(f"Errore: {directory} non è una cartella valida.")
            sys.exit(1)
        rename_files_in_directory(directory)
    else:
        root = tk.Tk()
        RenameApp(root)
        root.mainloop()


if __name__ == "__main__":
    main()