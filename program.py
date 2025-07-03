import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk
import os, re

# Mapping for trainer name decoding
charMap = {f"_{c}": c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
charMap.update({f"_{c.lower()}": c.lower() for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"})
charMap.update({f"_{d}": d for d in "0123456789"})
charMap.update({
    "_SPACE": " ",
    "_AMPERSAND": "&",
    "_PERIOD": ".",
})

# Reverse map used for encoding trainer names back to token strings
reverseCharMap = {v: k for k, v in charMap.items()}

def parseItemIds(path: str):
    # Extract unique ITEM_* identifiers from the reference file.
    pattern = re.compile(r'\.itemId\s*=\s*(ITEM_[A-Z0-9_]+)')
    items = []
    seen = set()
    with open(path, encoding='utf-8', errors='ignore') as f:
        for line in f:
            m = pattern.search(line)
            if m:
                item = m.group(1)
                if item not in seen:
                    seen.add(item)
                    items.append(item)
    return items

def itemDisplayName(item_id: str) -> str:
    # Convert an ITEM_* identifier into a user friendly name.
    return item_id.replace('ITEM_', '').replace('_', ' ').title()

def parseTrainerParties(path: str):
    # Parse trainer parties and return mapping of party name to mons.
    with open(path, encoding='utf-8', errors='ignore') as f:
        text = f.read()

    macros = {}
    macro_pattern = re.compile(r'#define\s+(\w+)\s*\\\n(.*?\})', re.S)
    for m in macro_pattern.finditer(text):
        body = m.group(2)
        mons = [
            {'level': int(l), 'species': s}
            for l, s in re.findall(r'\.lvl\s*=\s*(\d+).*?\.species\s*=\s*(SPECIES_[A-Z0-9_]+)', body, re.S)
        ]
        macros[m.group(1)] = mons

    parties = {}
    pattern = re.compile(r'struct\s+\w+\s+(sParty_\w+)\[\]\s*=\s*\{(.*?)\};', re.S)
    for m in pattern.finditer(text):
        name = m.group(1)
        body = m.group(2).strip()
        if body in macros:
            parties[name] = macros[body]
        else:
            parties[name] = [
                {'level': int(l), 'species': s}
                for l, s in re.findall(r'\.lvl\s*=\s*(\d+).*?\.species\s*=\s*(SPECIES_[A-Z0-9_]+)', body, re.S)
            ]
    return parties

def rewriteTrainerParty(path: str, party_name: str, mons: list, struct_type: str = None) -> None:
    # Rewrite a trainer party definition, optionally updating the struct type.
    pattern_start = re.compile(r'struct\s+(\w+)\s+' + re.escape(party_name) + r'\[\]\s*=\s*\{')
    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    inside = False
    start = end = None
    header_type = None
    for i, line in enumerate(lines):
        if not inside:
            m = pattern_start.search(line)
            if m:
                start = i
                header_type = m.group(1)
                inside = True
        else:
            if line.strip().startswith('};'):
                end = i
                break

    if start is None or end is None:
        return

    if struct_type is None:
        struct_type = header_type if header_type else 'TrainerMonNoItemDefaultMoves'

    new_lines = [f'struct {struct_type} {party_name}[] = {{\n']
    for mon in mons:
        new_lines.append('    {\n')
        new_lines.append(f'        .lvl = {mon["level"]},\n')
        new_lines.append(f'        .species = {mon["species"]},\n')
        new_lines.append('    },\n')
    new_lines.append('};\n')

    lines[start:end+1] = new_lines
    with open(path, 'w', encoding='utf-8', errors='ignore') as f:
        f.writelines(lines)

def parsePokemonNames(path: str) -> dict:
    # Parse the DPE Pokemon name table and return mapping of species id to name.
    names = {}
    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = [l.strip() for l in f]
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#org @NAME_'):
            spec = line.split('@NAME_')[1].strip()
            if not spec.startswith('SPECIES_'):
                spec = 'SPECIES_' + spec
            if i + 1 < len(lines):
                name = lines[i + 1].strip()
                if name:
                    names[spec] = name
                i += 1
        i += 1
    return names

def encodeTrainerName(name: str) -> str:
    # Encode a string into a comma-separated list of tokens.
    tokens = []
    for ch in name:
        if ch not in reverseCharMap:
            raise ValueError(f"Invalid character: {ch}")
        tokens.append(reverseCharMap[ch])
    tokens.append("_END")
    return ", ".join(tokens)

def decodeTrainerName(tokenStr: str) -> str:
    # Decode a comma-separated list of name tokens into a string.
    name = []
    for token in tokenStr.split(','):
        t = token.strip()
        if not t or t == '_END':
            break
        name.append(charMap.get(t, ''))
    return ''.join(name)

def flagsToUnionAndStruct(flags: str):
    has_item = 'PARTY_FLAG_HAS_ITEM' in flags
    custom_moves = 'PARTY_FLAG_CUSTOM_MOVES' in flags
    if has_item and custom_moves:
        return '.ItemCustomMoves', 'TrainerMonItemCustomMoves'
    elif has_item:
        return '.ItemDefaultMoves', 'TrainerMonItemDefaultMoves'
    elif custom_moves:
        return '.NoItemCustomMoves', 'TrainerMonNoItemCustomMoves'
    else:
        return '.NoItemDefaultMoves', 'TrainerMonNoItemDefaultMoves'

def parseTrainerData(path: str):
    # Parse the trainer data file and return list of dictionaries.
    trainers = []
    current_id = None
    current = None

    pattern_id = re.compile(r'\[(.+?)\]\s*=\s*\{')
    pattern_name = re.compile(r'\.trainerName\s*=\s*\{([^}]*)\}')
    pattern_gender = re.compile(r'\.gender\s*=\s*(GENDER_[A-Z]+)')
    pattern_items = re.compile(r'\.items\s*=\s*\{([^}]*)\}')
    pattern_double = re.compile(r'\.doubleBattle\s*=\s*(TRUE|FALSE)')
    pattern_partyflags = re.compile(r'\.partyFlags\s*=\s*([^,]+)')
    pattern_party = re.compile(r'\.party\s*=\s*\{[^=]*=\s*(sParty_[A-Za-z0-9_]+)')

    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    use_decap = any('#define DECAP_TRAINER_NAMES' in l for l in lines)

    in_decap_block = False
    active = True

    for line in lines:
        stripped = line.strip()

        if stripped.startswith('#ifdef DECAP_TRAINER_NAMES'):
            in_decap_block = True
            active = use_decap
            continue
        if stripped.startswith('#else') and in_decap_block:
            active = not use_decap
            continue
        if stripped.startswith('#endif') and in_decap_block:
            in_decap_block = False
            active = True
            continue

        m = pattern_id.search(line)
        if m:
            if current:
                trainers.append(current)
            current_id = m.group(1).strip()
            current = {'id': current_id}
            continue

        if not active or not current_id:
            continue

        if stripped.startswith('},'):
            trainers.append(current)
            current_id = None
            current = None
            continue

        m = pattern_name.search(line)
        if m:
            current['name'] = decodeTrainerName(m.group(1))
            continue
        m = pattern_gender.search(line)
        if m:
            current['gender'] = m.group(1)
            continue
        m = pattern_items.search(line)
        if m:
            current['items'] = [x.strip() for x in m.group(1).split(',')]
            continue
        m = pattern_double.search(line)
        if m:
            current['double'] = (m.group(1) == 'TRUE')
            continue
        m = pattern_partyflags.search(line)
        if m:
            current['partyFlags'] = m.group(1).strip()
            continue
        m = pattern_party.search(line)
        if m:
            current['party'] = m.group(1)
            continue
    if current:
        trainers.append(current)
    return trainers

def rewriteTrainerName(path: str, trainer_id: str, tokenStr: str) -> None:
    # Rewrite the trainerName entry for a given trainer id in the file.
    pattern_id = re.compile(rf"\[{re.escape(trainer_id)}\]\s*=\s*\{{")
    pattern_name = re.compile(r'(\.trainerName\s*=\s*\{)([^}]*)(\})')
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
                lines[i] = pattern_name.sub(rf"\1 {tokenStr} \3", line)
                break
    with open(path, 'w', encoding='utf-8', errors='ignore') as f:
        f.writelines(lines)

def rewriteTrainerOptions(path: str, trainerId: str, gender: str,
                          double: bool, partyFlags: str, items: list) -> None:
    # Rewrite various trainer options for a given trainer id.
    pattern_id = re.compile(rf"\[{re.escape(trainerId)}\]\s*=\s*\{{")
    pattern_gender = re.compile(r'(\.gender\s*=\s*)(GENDER_[A-Z]+)(,?)')
    pattern_double = re.compile(r'(\.doubleBattle\s*=\s*)(TRUE|FALSE)(,?)')
    pattern_partyflags = re.compile(r'(\.partyFlags\s*=\s*)([^,]+)(,?)')
    pattern_items = re.compile(r'(\.items\s*=\s*\{)([^}]*)(\})')
    pattern_party_union = re.compile(r'(\.party\s*=\s*\{\s*)(\.\w+)(\s*=\s*sParty_[A-Za-z0-9_]+)')

    with open(path, encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()

    inside = False
    for i, line in enumerate(lines):
        if not inside:
            if pattern_id.search(line):
                inside = True
        else:
            m = pattern_gender.search(line)
            if m:
                lines[i] = pattern_gender.sub(rf"\1{gender}\3", line)
                continue
            m = pattern_double.search(line)
            if m:
                val = 'TRUE' if double else 'FALSE'
                lines[i] = pattern_double.sub(rf"\1{val}\3", line)
                continue
            m = pattern_partyflags.search(line)
            if m:
                lines[i] = pattern_partyflags.sub(rf"\1{partyFlags}\3", line)
                continue
            m = pattern_items.search(line)
            if m:
                items_str = ', '.join(items)
                lines[i] = pattern_items.sub(rf"\1{items_str}\3", line)
                continue
            m = pattern_party_union.search(line)
            if m:
                union, _ = flagsToUnionAndStruct(partyFlags)
                lines[i] = pattern_party_union.sub(rf"\1{union}\3", line)
                continue
            if line.strip().startswith('},'):
                break

    with open(path, 'w', encoding='utf-8', errors='ignore') as f:
        f.writelines(lines)

# === Constants ===
defaultRelativePath = "src/Tables/trainer_data.c"
partyRelativePath = "src/Tables/trainer_parties.h"
spriteFolder = "sprites/"

# === Main Application Class ===
class TrainerEditor(tk.Tk):
    MAX_NAME_LEN = 10

    def __init__(self):
        super().__init__()
        style = ttk.Style(self)
        style.configure("Treeview.Heading", padding=(5, 2))
        self.title("Useful Trainer Editor")
        self.geometry("800x650")
        self.resizable(False, False)

        ref = os.path.join(os.path.dirname(__file__), "item_tables_reference.txt")
        self.item_ids = parseItemIds(ref) if os.path.exists(ref) else ["ITEM_NONE"]
        self.item_names = [itemDisplayName(i) for i in self.item_ids]
        self.id_from_name = dict(zip(self.item_names, self.item_ids))
        self.name_from_id = dict(zip(self.item_ids, self.item_names))

        self.trainer_data = []
        self.parties = {}
        self.species_names = []
        self.species_name_map = {}
        self.name_from_species = {}
        self.species_from_name = {}
        self.current_trainer_index = None
        self.createMenu()
        self.createPanes()
        self.createWidgets()
        self.centerWindow()
        self.after(100, self.startupFolders)

    def centerWindow(self):
        # Center the window on the user's screen.
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def startupFolders(self):
        # Prompt the user to select CFRU and DPE folders when launching.
        self.openCfruFolder()
        self.openDpeFolder()

    def createMenu(self):
        menubar = tk.Menu(self)
        fileMenu = tk.Menu(menubar, tearoff=0)
        fileMenu.add_command(label="Open CFRU Folder", command=self.openCfruFolder)
        fileMenu.add_command(label="Open DPE Folder", command=self.openDpeFolder)
        fileMenu.add_separator()
        fileMenu.add_command(label="Exit", command=self.quit)
        menubar.add_cascade(label="File", menu=fileMenu)
        trainerMenu = tk.Menu(menubar, tearoff=0)
        trainerMenu.add_command(label="Randomize", command=self.randomize)
        menubar.add_cascade(label="Trainer", menu=trainerMenu)
        settingsMenu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Settings", menu=settingsMenu)
        helpMenu = tk.Menu(menubar, tearoff=0)
        helpMenu.add_command(label="About")
        menubar.add_cascade(label="Help", menu=helpMenu)
        self.config(menu=menubar)

    def createPanes(self):
        # Use tk.PanedWindow to allow sashwidth
        self.panes = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=0)
        self.panes.pack(fill=tk.BOTH, expand=True)

        # Left frame: fixed width list
        self.frameLeft = tk.Frame(self.panes, width=200)
        self.frameLeft.pack_propagate(False)
        self.trainerList = ttk.Treeview(
            self.frameLeft,
            columns=("ID","Name"),
            show="headings",
            height=25
        )
        self.trainerList.heading("ID", text="ID", anchor="center")
        self.trainerList.heading("Name", text="Trainer", anchor="center")
        self.trainerList.column("ID", anchor="center", width=50)
        self.trainerList.column("Name", anchor="center", width=130)
        # scrollbar if needed
        scrollbar = ttk.Scrollbar(self.frameLeft, orient=tk.VERTICAL, command=self.trainerList.yview)
        self.trainerList.configure(yscrollcommand=scrollbar.set)
        self.trainerList.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.trainerList.bind("<<TreeviewSelect>>", self.on_select_trainer)
        self.panes.add(self.frameLeft, stretch='never')

        # Right frame: details
        self.frameRight = tk.Frame(self.panes)
        self.panes.add(self.frameRight, stretch='always')
        self.frameRight.grid_columnconfigure(0, weight=1)
        self.frameRight.grid_columnconfigure(1, weight=1)
        self.frameRight.grid_rowconfigure(2, weight=1)

    def createWidgets(self):
        # DETAIL PANES: Use labelframes for each section
        # Basics
        self.frameBasics = ttk.LabelFrame(self.frameRight, text="Basics")
        self.frameBasics.grid(row=0, column=0, padx=10, pady=5, sticky="nwe")
        ttk.Label(self.frameBasics, text="Sprite:").grid(row=0, column=0, sticky="w")
        self.lblSprite = ttk.Label(self.frameBasics)
        self.lblSprite.grid(row=0, column=1)
        ttk.Label(self.frameBasics, text="Name:").grid(row=1, column=0, sticky="w")
        self.entryName = ttk.Entry(self.frameBasics)
        self.entryName.bind("<FocusOut>", self.onNameFocusOut)
        self.entryName.grid(row=1, column=1, columnspan=2, sticky="we")
        ttk.Label(self.frameBasics, text="Gender:").grid(row=2, column=0, sticky="w")
        self.genderVar = tk.StringVar()
        ttk.Radiobutton(self.frameBasics, text="Male", variable=self.genderVar, value="M").grid(row=2, column=1)
        ttk.Radiobutton(self.frameBasics, text="Female", variable=self.genderVar, value="F").grid(row=2, column=2)

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
            combo = ttk.Combobox(self.frameItems, textvariable=var, values=self.item_names, state="readonly")
            combo.grid(row=i, column=1)
            self.itemVars.append(var)

        # Options
        self.frameOptions = ttk.LabelFrame(self.frameRight, text="Options")
        self.frameOptions.grid(row=1, column=1, padx=10, pady=5, sticky="nwe")
        ttk.Label(self.frameOptions, text="Music ID:").grid(row=0, column=0)
        self.spinMusic = tk.Spinbox(self.frameOptions, from_=0, to=255, width=5)
        self.spinMusic.grid(row=0, column=1)
        self.doubleVar = tk.BooleanVar()
        self.customItemVar = tk.BooleanVar()
        self.customMoveVar = tk.BooleanVar()
        self.chkDouble = ttk.Checkbutton(self.frameOptions, text="Double Battle", variable=self.doubleVar)
        ttk.Label(self.frameOptions, text="AI Flags:").grid(row=1, column=0)
        self.spinAI = tk.Spinbox(self.frameOptions, from_=0, to=255, width=5)
        self.spinAI.grid(row=1, column=1)
        self.chkCustomItems = ttk.Checkbutton(self.frameOptions, text="Custom Held Items", variable=self.customItemVar)
        self.chkCustomMoves = ttk.Checkbutton(self.frameOptions, text="Custom Movesets", variable=self.customMoveVar)
        self.chkDouble.grid(row=2, column=0, sticky="w")
        self.chkCustomItems.grid(row=2, column=1, sticky="w")
        self.chkCustomMoves.grid(row=2, column=2, sticky="w")

        # Party
        self.frameParty = ttk.LabelFrame(self.frameRight, text="Party")
        self.frameParty.grid(row=3, column=0, columnspan=2, padx=10, pady=5, sticky="nsew")
        self.frameParty.grid_rowconfigure(1, weight=1)

        self.partyTree = ttk.Treeview(self.frameParty, columns=("Species", "Level"), show="headings", height=6)
        self.partyTree.heading("Species", text="Species", anchor="center")
        self.partyTree.heading("Level", text="Level", anchor="center")
        self.partyTree.column("Species", anchor="center")
        self.partyTree.column("Level", anchor="center")
        self.partyTree.grid(row=0, column=0, columnspan=4)

        btnAdd = ttk.Button(self.frameParty, text="+ Add", command=self.add_party_mon)
        btnAdd.grid(row=2, column=0)
        btnRemove = ttk.Button(self.frameParty, text="- Remove", command=self.remove_party_mon)
        btnRemove.grid(row=2, column=1)
        btnUpdate = ttk.Button(self.frameParty, text="Update", command=self.update_party_mon)
        btnUpdate.grid(row=2, column=2)
        self.partyTree.bind("<<TreeviewSelect>>", self.on_party_select)

        ttk.Label(self.frameParty, text="Species:").grid(row=3, column=0)
        self.comboSpecies = ttk.Combobox(self.frameParty, values=self.species_names, state="readonly")
        self.comboSpecies.grid(row=3, column=1)
        ttk.Label(self.frameParty, text="Level:").grid(row=3, column=2)
        self.spinLevel = tk.Spinbox(self.frameParty, from_=1, to=100, width=5)
        self.spinLevel.grid(row=3, column=3)

        ttk.Label(self.frameParty, text="EVs:").grid(row=4, column=0)
        self.spinEVs = tk.Spinbox(self.frameParty, from_=0, to=255, width=5)
        self.spinEVs.grid(row=4, column=1)
        ttk.Label(self.frameParty, text="Held Item:").grid(row=4, column=2)
        self.comboHeld = ttk.Combobox(self.frameParty, values=self.item_names, state="readonly")
        self.comboHeld.grid(row=4, column=3)

        ttk.Label(self.frameParty, text="Attacks:").grid(row=5, column=0)
        for i in range(4):
            combo = ttk.Combobox(self.frameParty, values=["MOVE_TACKLE", "..."])
            combo.grid(row=5 + i//2, column=1 + i%2)

        # Single save button for all edits
        self.btnSaveAll = ttk.Button(self.frameRight, text="Save", command=self.saveAll)
        self.btnSaveAll.grid(row=2, column=1, sticky="e", padx=10, pady=(0,5))

    def on_select_trainer(self, event):
        sel = self.trainerList.selection()
        if not sel:
            return
        idx = self.trainerList.index(sel[0])
        self.current_trainer_index = idx
        data = self.trainer_data[idx]
        self.entryName.delete(0, tk.END)
        self.entryName.insert(0, data.get('name', ''))
        gender = data.get('gender', 'GENDER_MALE')
        self.genderVar.set('M' if gender == 'GENDER_MALE' else 'F')
        self.doubleVar.set(data.get('double', False))
        flags = data.get('partyFlags', '0')
        self.customItemVar.set('PARTY_FLAG_HAS_ITEM' in flags)
        self.customMoveVar.set('PARTY_FLAG_CUSTOM_MOVES' in flags)
        items = data.get('items', [])
        for var, item in zip(self.itemVars, items):
            var.set(self.name_from_id.get(item, item))
        for var in self.itemVars[len(items):]:
            var.set(self.name_from_id.get('ITEM_NONE', 'None'))
        self.partyTree.delete(*self.partyTree.get_children())
        party_name = data.get('party')
        if party_name and party_name in self.parties:
            for mon in self.parties[party_name]:
                disp = self.name_from_species.get(mon['species'], mon['species'])
                self.partyTree.insert('', 'end', values=(disp, mon['level']))

    def add_party_mon(self):
        species = self.comboSpecies.get()
        level = self.spinLevel.get()
        if not species or not level:
            return
        self.partyTree.insert('', 'end', values=(species, level))

    def remove_party_mon(self):
        sel = self.partyTree.selection()
        if sel:
            self.partyTree.delete(sel[0])

    def on_party_select(self, event):
        sel = self.partyTree.selection()
        if not sel:
            return
        species, level = self.partyTree.item(sel[0], 'values')
        self.comboSpecies.set(species)
        self.spinLevel.delete(0, tk.END)
        self.spinLevel.insert(0, level)

    def update_party_mon(self):
        sel = self.partyTree.selection()
        if not sel:
            return
        species = self.comboSpecies.get()
        level = self.spinLevel.get()
        if not species or not level:
            return
        self.partyTree.item(sel[0], values=(species, level))

    def saveTrainerName(self):
        if self.current_trainer_index is None:
            return
        new_name = self.entryName.get()
        try:
            encoded = encodeTrainerName(new_name)
        except ValueError as e:
            messagebox.showerror("Invalid Name", str(e))
            return

        data = self.trainer_data[self.current_trainer_index]
        tid = data['id']
        data['name'] = new_name
        display = new_name if new_name else "???"
        item_id = self.trainerList.get_children()[self.current_trainer_index]
        self.trainerList.item(item_id, values=(self.current_trainer_index, display))

        if self.cfruFolder:
            path = os.path.join(self.cfruFolder, defaultRelativePath)
            rewriteTrainerName(path, tid, encoded)

    def saveOptions(self):
        if self.current_trainer_index is None:
            return
        data = self.trainer_data[self.current_trainer_index]
        data['gender'] = 'GENDER_MALE' if self.genderVar.get() == 'M' else 'GENDER_FEMALE'
        data['double'] = self.doubleVar.get()
        flags = []
        if self.customItemVar.get():
            flags.append('PARTY_FLAG_HAS_ITEM')
        if self.customMoveVar.get():
            flags.append('PARTY_FLAG_CUSTOM_MOVES')
        data['partyFlags'] = ' | '.join(flags) if flags else '0'
        data['items'] = [self.id_from_name.get(var.get(), 'ITEM_NONE') for var in self.itemVars]

        if self.cfruFolder:
            path = os.path.join(self.cfruFolder, defaultRelativePath)
            rewriteTrainerOptions(path, data['id'], data['gender'], data['double'], data['partyFlags'], data['items'])
            party_name = data.get('party')
            if party_name and party_name in self.parties:
                party_path = os.path.join(self.cfruFolder, partyRelativePath)
                union, struct_type = flagsToUnionAndStruct(data['partyFlags'])
                mons = self.parties[party_name]
                rewriteTrainerParty(party_path, party_name, mons, struct_type)

    def saveParty(self):
        if self.current_trainer_index is None:
            return
        data = self.trainer_data[self.current_trainer_index]
        party_name = data.get('party')
        if not party_name:
            return
        mons = []
        for item in self.partyTree.get_children():
            species, level = self.partyTree.item(item, 'values')
            spec_id = self.species_from_name.get(species, species)
            mons.append({'level': int(level), 'species': spec_id})
        self.parties[party_name] = mons
        if self.cfruFolder:
            path = os.path.join(self.cfruFolder, partyRelativePath)
            union, struct_type = flagsToUnionAndStruct(data.get('partyFlags', '0'))
            rewriteTrainerParty(path, party_name, mons, struct_type)

    def saveAll(self):
        # Save name and option edits.
        self.saveTrainerName()
        self.saveOptions()
        self.saveParty()

    # === Placeholder command methods ===
    def openCfruFolder(self):
        # Prompt the user to select the base CFRU folder and load files.
        self.selectCfruFolder()

    def openDpeFolder(self):
        # Prompt the user to select the DPE folder and load name data.
        self.selectDpeFolder()

    def selectCfruFolder(self):
        # Open a folder selection dialog and validate required files.
        folder = filedialog.askdirectory(title="Select CFRU folder")
        if not folder:
            return

        trainer_data_path = os.path.join(folder, defaultRelativePath)
        trainer_parties_path = os.path.join(folder, partyRelativePath)
        if not os.path.isfile(trainer_data_path):
            messagebox.showerror(
                "File Not Found",
                f"Could not locate trainer data at:\n{trainer_data_path}"
            )
            return
        if not os.path.isfile(trainer_parties_path):
            messagebox.showerror(
                "File Not Found",
                f"Could not locate trainer parties at:\n{trainer_parties_path}"
            )
            return

        self.cfruFolder = folder
        self.parties = parseTrainerParties(trainer_parties_path)
        species = {mon['species'] for mons in self.parties.values() for mon in mons}
        self.species_names = sorted(species)
        self.updateSpeciesBox()
        self.comboHeld['values'] = self.item_names
        self.loadTrainerData(trainer_data_path)
        messagebox.showinfo(
            "Success",
            f"Loaded {len(self.trainer_data)} trainers from {folder}!"
        )

    def updateSpeciesBox(self):
        # Update species combobox options based on loaded names.
        if self.species_name_map:
            names = [self.species_name_map.get(s, s) for s in self.species_names]
            self.comboSpecies['values'] = names
        else:
            self.comboSpecies['values'] = self.species_names

    def selectDpeFolder(self):
        # Open a folder selection dialog for the DPE folder.
        folder = filedialog.askdirectory(title="Select DPE folder")
        if not folder:
            return

        name_path = os.path.join(folder, 'strings', 'Pokemon_Name_Table.string')
        if not os.path.isfile(name_path):
            messagebox.showerror(
                "File Not Found",
                f"Could not locate Pokemon name table at:\n{name_path}"
            )
            return

        self.dpeFolder = folder
        self.species_name_map = parsePokemonNames(name_path)
        self.name_from_species = self.species_name_map
        self.species_from_name = {v: k for k, v in self.species_name_map.items()}
        self.updateSpeciesBox()

    def loadTrainerData(self, path: str):
        # Parse trainer data file and populate the tree view.
        self.trainer_data.clear()
        self.trainerList.delete(*self.trainerList.get_children())
        try:
            trainers = parseTrainerData(path)
        except Exception as e:
            messagebox.showerror("Parse Error", f"Failed to parse trainer data:\n{e}")
            return

        for idx, data in enumerate(trainers):
            self.trainer_data.append(data)
            display_name = data.get('name', '') or "???"
            self.trainerList.insert("", "end", values=(idx, display_name))

    def randomize(self):
        messagebox.showinfo("Randomize", "Party randomized!")

    def onNameFocusOut(self, event):
        name = self.entryName.get()
        if len(name) > self.MAX_NAME_LEN:
            truncated = name[:self.MAX_NAME_LEN]
            self.entryName.delete(0, tk.END)
            self.entryName.insert(0, truncated)
            messagebox.showinfo("Name truncated", f"Name truncated to {truncated}")

# === Application Entry Point ===
if __name__ == '__main__':
    app = TrainerEditor()
    app.mainloop()
