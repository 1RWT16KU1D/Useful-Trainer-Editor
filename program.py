import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os, re

# Mapping for trainer name decoding
_CHAR_MAP = {f"_{c}": c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_CHAR_MAP.update({f"_{c.lower()}": c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
_CHAR_MAP.update({f"_{d}": d for d in "0123456789"})
_CHAR_MAP.update({
    "_SPACE": " ",
    "_AMPERSAND": "&",
    "_PERIOD": ".",
})

# Reverse map used for encoding trainer names back to token strings
_REVERSE_CHAR_MAP = {v: k for k, v in _CHAR_MAP.items()}

def encode_trainer_name(name: str) -> str:
    """Encode a string into a comma-separated list of tokens."""
    tokens = []
    for ch in name:
        if ch not in _REVERSE_CHAR_MAP:
            raise ValueError(f"Invalid character: {ch}")
        tokens.append(_REVERSE_CHAR_MAP[ch])
    tokens.append("_END")
    return ", ".join(tokens)

def decode_trainer_name(token_str: str) -> str:
    """Decode a comma-separated list of name tokens into a string."""
    name = []
    for token in token_str.split(','):
        t = token.strip()
        if not t or t == '_END':
            break
        name.append(_CHAR_MAP.get(t, ''))
    return ''.join(name)

def parse_trainer_data(path: str):
    """Return list of (trainer_id, trainer_name) from the given file."""
    trainers = []
    current_id = None
    pattern_id = re.compile(r'\[(.+?)\]\s*=\s*\{')
    pattern_name = re.compile(r'\.trainerName\s*=\s*\{([^}]*)\}')
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = pattern_id.search(line)
            if m:
                current_id = m.group(1).strip()
                continue
            if current_id:
                m = pattern_name.search(line)
                if m:
                    name = decode_trainer_name(m.group(1))
                    trainers.append((current_id, name))
                    current_id = None
    return trainers

def rewrite_trainer_name(path: str, trainer_id: str, token_str: str) -> None:
    """Rewrite the trainerName entry for a given trainer id in the file."""
    pattern_id = re.compile(rf"\[{re.escape(trainer_id)}\]\s*=\s*\{{")
    pattern_name = re.compile(r'(\.trainerName\s*=\s*\{)([^}]*)(\})')
    lines = []
    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    inside = False
    for i, line in enumerate(lines):
        if not inside:
            if pattern_id.search(line):
                inside = True
        else:
            m = pattern_name.search(line)
            if m:
                lines[i] = pattern_name.sub(rf"\1 {token_str} \3", line)
                break

    with open(path, 'w', encoding='utf-8', errors='ignore') as f:
        f.writelines(lines)

# === Constants ===
defaultRelativePath = "src/Tables/trainer_data.c"
spriteFolder = "sprites/"

# === Main Application Class ===
class TrainerEditor(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Hopeless Trainer Editor - CFRU Mod")
        self.geometry("800x600")
        self.resizable(False, False)
        self._create_menu()
        self._create_panes()
        self._create_widgets()
        # Cache of loaded trainer data
        self.trainer_data = []
        self.current_trainer_index = None

    def _create_menu(self):
        menubar = tk.Menu(self)
        # File Menu
        fileMenu = tk.Menu(menubar, tearoff=0)
        fileMenu.add_command(label="Open CFRU Folder", command=self.open_folder)
        fileMenu.add_separator()
        fileMenu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=fileMenu)
        # Trainer Menu
        trainerMenu = tk.Menu(menubar, tearoff=0)
        trainerMenu.add_command(label="Randomize", command=self.randomize)
        menubar.add_cascade(label="Trainer", menu=trainerMenu)
        # Settings Menu (placeholder)
        settingsMenu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settingsMenu)
        # Help Menu
        helpMenu = tk.Menu(menubar, tearoff=0)
        helpMenu.add_command(label="About")
        menubar.add_cascade(label="Help", menu=helpMenu)
        self.config(menu=menubar)

    def _create_panes(self):
        # Main horizontal paned window
        self.panes = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        self.panes.pack(fill=tk.BOTH, expand=True)

        # Left frame: Trainer list
        self.frameLeft = tk.Frame(self.panes, width=200)
        self.trainerList = ttk.Treeview(self.frameLeft, columns=("#","Name"), show="headings")
        self.trainerList.heading("#", text="#")
        self.trainerList.heading("Name", text="Trainer")
        self.trainerList.pack(fill=tk.BOTH, expand=True)
        self.trainerList.bind("<<TreeviewSelect>>", self.on_select_trainer)
        self.panes.add(self.frameLeft, weight=1)

        # Right frame: Details
        self.frameRight = tk.Frame(self.panes)
        self.panes.add(self.frameRight, weight=3)
        self.frameRight.grid_columnconfigure(0, weight=1)
        self.frameRight.grid_columnconfigure(1, weight=1)
        self.frameRight.grid_rowconfigure(2, weight=1)

    def _create_widgets(self):
        # DETAIL PANES: Use labelframes for each section
        # Basics
        self.frameBasics = ttk.LabelFrame(self.frameRight, text="Basics")
        self.frameBasics.grid(row=0, column=0, padx=10, pady=5, sticky="nwe")
        ttk.Label(self.frameBasics, text="Sprite:").grid(row=0, column=0, sticky="w")
        self.lblSprite = ttk.Label(self.frameBasics)
        self.lblSprite.grid(row=0, column=1)
        ttk.Label(self.frameBasics, text="Name:").grid(row=1, column=0, sticky="w")
        self.entryName = ttk.Entry(self.frameBasics)
        self.entryName.grid(row=1, column=1)
        btnSave = ttk.Button(self.frameBasics, text="Save", command=self.save_trainer_name)
        btnSave.grid(row=1, column=2, padx=(5,0))
        ttk.Label(self.frameBasics, text="Gender:").grid(row=2, column=0, sticky="w")
        self.genderVar = tk.StringVar()
        ttk.Radiobutton(self.frameBasics, text="Male", variable=self.genderVar, value="M").grid(row=2, column=1)
        ttk.Radiobutton(self.frameBasics, text="Female", variable=self.genderVar, value="F").grid(row=2, column=2)
        ttk.Label(self.frameBasics, text="# ID:").grid(row=3, column=0, sticky="w")
        self.spinId = tk.Spinbox(self.frameBasics, from_=0, to=255, width=5)
        self.spinId.grid(row=3, column=1)

        # Class
        self.frameClass = ttk.LabelFrame(self.frameRight, text="Class")
        self.frameClass.grid(row=1, column=0, padx=10, pady=5, sticky="nwe")
        ttk.Label(self.frameClass, text="Class ID:").grid(row=0, column=0, sticky="w")
        self.spinClassId = tk.Spinbox(self.frameClass, from_=0, to=255, width=5)
        self.spinClassId.grid(row=0, column=1)
        self.comboClass = ttk.Combobox(self.frameClass, values=["TRAINER_CLASS_YOUNGSTER", "TRAINER_CLASS_BUG_MANIAC", "..."])
        self.comboClass.grid(row=0, column=2)
        self.entryClassName = ttk.Entry(self.frameClass)
        self.entryClassName.grid(row=1, column=0, columnspan=3, sticky="we")

        # Items
        self.frameItems = ttk.LabelFrame(self.frameRight, text="Items")
        self.frameItems.grid(row=0, column=1, padx=10, pady=5, sticky="nwe")
        self.itemVars = []
        for i in range(4):
            ttk.Label(self.frameItems, text=f"Item {i+1}:").grid(row=i, column=0, sticky="w")
            var = tk.StringVar()
            combo = ttk.Combobox(self.frameItems, textvariable=var, values=["ITEM_NONE", "ITEM_POTION", "..."])
            combo.grid(row=i, column=1)
            self.itemVars.append(var)

        # Options
        self.frameOptions = ttk.LabelFrame(self.frameRight, text="Options")
        self.frameOptions.grid(row=1, column=1, padx=10, pady=5, sticky="nwe")
        ttk.Label(self.frameOptions, text="Music ID:").grid(row=0, column=0)
        self.spinMusic = tk.Spinbox(self.frameOptions, from_=0, to=255, width=5)
        self.spinMusic.grid(row=0, column=1)
        self.chkDouble = ttk.Checkbutton(self.frameOptions, text="Double Battle")
        self.chkDouble.grid(row=0, column=2)
        ttk.Label(self.frameOptions, text="AI Flags:").grid(row=1, column=0)
        self.spinAI = tk.Spinbox(self.frameOptions, from_=0, to=255, width=5)
        self.spinAI.grid(row=1, column=1)
        self.chkCustomItems = ttk.Checkbutton(self.frameOptions, text="Custom Held Items")
        self.chkCustomItems.grid(row=1, column=2)
        self.chkCustomMoves = ttk.Checkbutton(self.frameOptions, text="Custom Movesets")
        self.chkCustomMoves.grid(row=2, column=2)

        # Party
        self.frameParty = ttk.LabelFrame(self.frameRight, text="Party")
        self.frameParty.grid(row=2, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.partyTree = ttk.Treeview(self.frameParty, columns=("Species","Level"), show="headings", height=5)
        self.partyTree.heading("Species", text="Species")
        self.partyTree.heading("Level", text="Level")
        self.partyTree.grid(row=0, column=0, columnspan=4)
        btnAdd = ttk.Button(self.frameParty, text="+ Add")
        btnAdd.grid(row=1, column=0)
        btnRemove = ttk.Button(self.frameParty, text="- Remove")
        btnRemove.grid(row=1, column=1)
        ttk.Label(self.frameParty, text="Species:").grid(row=2, column=0)
        self.comboSpecies = ttk.Combobox(self.frameParty, values=["SPECIES_BULBASAUR", "..."])
        self.comboSpecies.grid(row=2, column=1)
        ttk.Label(self.frameParty, text="Level:").grid(row=2, column=2)
        self.spinLevel = tk.Spinbox(self.frameParty, from_=1, to=100, width=5)
        self.spinLevel.grid(row=2, column=3)
        ttk.Label(self.frameParty, text="EVs:").grid(row=3, column=0)
        self.spinEVs = tk.Spinbox(self.frameParty, from_=0, to=255, width=5)
        self.spinEVs.grid(row=3, column=1)
        ttk.Label(self.frameParty, text="Held Item:").grid(row=3, column=2)
        self.comboHeld = ttk.Combobox(self.frameParty, values=["ITEM_NONE", "..."])
        self.comboHeld.grid(row=3, column=3)
        ttk.Label(self.frameParty, text="Attacks:").grid(row=4, column=0)
        for i in range(4):
            combo = ttk.Combobox(self.frameParty, values=["MOVE_TACKLE", "..."])
            combo.grid(row=4 + i//2, column=1 + i%2)

    def on_select_trainer(self, event):
        sel = self.trainerList.selection()
        if not sel:
            return
        idx = self.trainerList.index(sel[0])
        self.current_trainer_index = idx
        tid, name = self.trainer_data[idx]
        self.entryName.delete(0, tk.END)
        self.entryName.insert(0, name)

    def save_trainer_name(self):
        if self.current_trainer_index is None:
            return
        new_name = self.entryName.get()
        try:
            encoded = encode_trainer_name(new_name)
        except ValueError as e:
            messagebox.showerror("Invalid Name", str(e))
            return

        tid, _ = self.trainer_data[self.current_trainer_index]
        self.trainer_data[self.current_trainer_index] = (tid, new_name)
        display = new_name if new_name else "???"
        item_id = self.trainerList.get_children()[self.current_trainer_index]
        self.trainerList.item(item_id, values=(self.current_trainer_index, display))

        if hasattr(self, 'selectedFolder'):
            path = os.path.join(self.selectedFolder, defaultRelativePath)
            rewrite_trainer_name(path, tid, encoded)

    # === Placeholder command methods ===
    def open_folder(self):
        """Prompt the user to select the base CFRU folder and load files."""
        self.selectFolder()

    def selectFolder(self):
        """Open a folder selection dialog and validate required files."""
        folder = filedialog.askdirectory(title="Select CFRU folder")
        if not folder:
            return

        trainer_data_path = os.path.join(folder, defaultRelativePath)
        if not os.path.isfile(trainer_data_path):
            messagebox.showerror(
                "File Not Found",
                f"Could not locate trainer data at:\n{trainer_data_path}"
            )
            return

        self.selectedFolder = folder
        self.load_trainer_data(trainer_data_path)
        messagebox.showinfo(
            "Folder Opened",
            f"Loaded trainer data from:\n{trainer_data_path}"
        )

    def load_trainer_data(self, path: str):
        """Parse trainer data file and populate the tree view."""
        self.trainer_data.clear()
        self.trainerList.delete(*self.trainerList.get_children())
        try:
            trainers = parse_trainer_data(path)
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse trainer data:\n{e}")
            return

        for idx, (tid, name) in enumerate(trainers):
            self.trainer_data.append((tid, name))
            display_name = name if name else "???"
            self.trainerList.insert("", "end", values=(idx, display_name))

    def randomize(self):
        messagebox.showinfo("Randomize", "Party randomized!")

# === Application Entry Point ===
if __name__ == '__main__':
    app = TrainerEditor()
    app.mainloop()
