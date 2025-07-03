import tkinter as tk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import re
import os

defaultRelativePath = "src/Tables/trainer_data.c"
spriteFolder = "sprites/"

gbaCharMap = {
    "_A": "A", "_B": "B", "_C": "C", "_D": "D", "_E": "E", "_F": "F", "_G": "G", "_H": "H", "_I": "I", "_J": "J",
    "_K": "K", "_L": "L", "_M": "M", "_N": "N", "_O": "O", "_P": "P", "_Q": "Q", "_R": "R", "_S": "S", "_T": "T",
    "_U": "U", "_V": "V", "_W": "W", "_X": "X", "_Y": "Y", "_Z": "Z",
    "_a": "a", "_b": "b", "_c": "c", "_d": "d", "_e": "e", "_f": "f", "_g": "g", "_h": "h", "_i": "i", "_j": "j",
    "_k": "k", "_l": "l", "_m": "m", "_n": "n", "_o": "o", "_p": "p", "_q": "q", "_r": "r", "_s": "s", "_t": "t",
    "_u": "u", "_v": "v", "_w": "w", "_x": "x", "_y": "y", "_z": "z",
    "_0": "0", "_1": "1", "_2": "2", "_3": "3", "_4": "4", "_5": "5", "_6": "6", "_7": "7", "_8": "8", "_9": "9",
    "_SPACE": " ", "_PERIOD": ".", "_EXCLAMATION": "!", "_QUESTION": "?", "_HYPHEN": "-", "_AMPERSAND": "&",
    "_APOSTROPHE": "'", "_TIMES": "×", "_NEWLINE": "\n",
    "_AT": "@", "_eACUTE": "é", "_PO": "PO", "_KE": "KE", "_BL": "BL", "_OC": "OC", "_OK": "OK",
    "_END": ""
}

def decodeMacroName(charArray: str) -> str:
    tokens = re.findall(r'_(\w+)', charArray)
    return ''.join(gbaCharMap.get(f"_{token}", '?') for token in tokens)

def parseTrainers(filePath):
    """Parse trainer definitions from the given file."""
    trainers = []
    start_re = re.compile(r"\[(.+?)\]\s*=\s*\{")

    with open(filePath, encoding="utf-8") as f:
        lines = f.readlines()

    collecting = False
    brace_count = 0
    body_lines = []
    identifier = ""

    for line in lines:
        if not collecting:
            match = start_re.search(line)
            if match:
                collecting = True
                identifier = match.group(1)
                brace_count = 1
                body_lines = []
                continue
        else:
            body_lines.append(line)
            brace_count += line.count('{')
            brace_count -= line.count('}')

            if brace_count == 0:
                body = ''.join(body_lines)

                nameMatch = re.search(r'\.trainerName\s*=\s*\{([^}]+)\}', body)
                classMatch = re.search(r'\.trainerClass\s*=\s*(\w+)', body)
                spriteMatch = re.search(r'\.trainerPic\s*=\s*(\w+)', body)

                trainerName = decodeMacroName(nameMatch.group(1)) if nameMatch else "Unknown"
                
                if trainerName == "":
                    trainerName = "???"

                trainers.append({
                    "id": identifier.strip(),
                    "name": trainerName,
                    "class": classMatch.group(1) if classMatch else "???",
                    "sprite": spriteMatch.group(1).lower() + ".png" if spriteMatch else None,
                })

                collecting = False
                brace_count = 0
                body_lines = []
                identifier = ""

    return trainers

class TrainerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Useful Trainer Editor")
        self.geometry("550x450")
        self.trainers = []
        self.setupUI()

    def setupUI(self):
        topFrame = tk.Frame(self)
        topFrame.pack(pady=10)

        browseBtn = tk.Button(topFrame, text="Open CFRU Folder", command=self.selectFolder)
        browseBtn.pack()

        self.listBox = tk.Listbox(self, width=50)
        self.listBox.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=10)
        self.listBox.bind("<<ListboxSelect>>", self.displayTrainer)

        self.infoLabel = tk.Label(self, text="No trainer loaded yet", font=("Arial", 12))
        self.infoLabel.pack(pady=10)

        self.imageLabel = tk.Label(self)
        self.imageLabel.pack()

    def selectFolder(self):
        folderPath = filedialog.askdirectory(title="Select your CFRU folder")
        if not folderPath:
            return

        trainerFile = os.path.join(folderPath, defaultRelativePath)
        if not os.path.exists(trainerFile):
            messagebox.showerror("Error", f"Trainer file not found:\n{trainerFile}")
            return

        self.trainers = parseTrainers(trainerFile)
        self.listBox.delete(0, tk.END)

        for trainer in self.trainers:
            self.listBox.insert(tk.END, f"{trainer['name']} ({trainer['id']})")

        messagebox.showinfo("Success", f"Loaded {len(self.trainers)} trainers.")

    def displayTrainer(self, event):
        index = self.listBox.curselection()
        if not index:
            return

        trainer = self.trainers[index[0]]
        infoText = f"Trainer Name: {trainer['name']}\nClass: {trainer['class']}"
        self.infoLabel.config(text=infoText)

        spritePath = os.path.join(spriteFolder, trainer['sprite']) if trainer['sprite'] else None
        if spritePath and os.path.exists(spritePath):
            img = Image.open(spritePath).resize((96, 96))
            self.spriteImg = ImageTk.PhotoImage(img)
            self.imageLabel.config(image=self.spriteImg)
        else:
            self.imageLabel.config(image='')

if __name__ == "__main__":
    app = TrainerApp()
    app.mainloop()
