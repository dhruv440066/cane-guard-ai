"""Dataset discovery, cleaning and splitting (no TensorFlow needed)."""
from pathlib import Path
from PIL import Image
from sklearn.model_selection import train_test_split
EXT = {".jpg", ".jpeg", ".png", ".bmp"}
SPLIT_NAMES = {"train": "train", "training": "train", "val": "val", "valid": "val", "validation": "val", "test": "test", "testing": "test"}

def _images(d): return [p for p in Path(d).rglob("*") if p.is_file() and p.suffix.lower() in EXT]

def find_root(start):
    """Shallowest folder that holds >=2 image folders. Returns (folder, 'classes' | 'presplit')."""
    queue = [Path(start)]
    while queue:
        d = queue.pop(0)
        subs = [c for c in sorted(d.iterdir()) if c.is_dir()]
        with_imgs = [c for c in subs if _images(c)]
        if len(with_imgs) >= 2:
            if all(c.name.lower() in SPLIT_NAMES for c in with_imgs): return d, "presplit"
            return d, "classes"
        queue += subs
    raise SystemExit(f"No class folders with images found under: {start}")

def collect(root, mode):
    """Returns (classes, {'train':[(path,label)], 'val':[...], 'test':[...]}) with unreadable images removed."""
    root = Path(root); data = {"train": [], "val": [], "test": []}; bad = []
    def add(split, folder, classes):
        for lab, c in enumerate(classes):
            for p in _images(Path(folder) / c):
                try:
                    with Image.open(p) as im: im.verify()
                    data[split].append((str(p), lab))
                except Exception: bad.append(str(p))
    if mode == "classes":
        classes = [c.name for c in sorted(root.iterdir()) if c.is_dir() and _images(c)]
        add("train", root, classes)
    else:
        folders = {SPLIT_NAMES[c.name.lower()]: c for c in root.iterdir() if c.is_dir() and c.name.lower() in SPLIT_NAMES}
        classes = [c.name for c in sorted(folders["train"].iterdir()) if c.is_dir() and _images(c)]
        for s, f in folders.items(): add(s, f, classes)
    return classes, data, bad

def make_splits(data, seed=42):
    """If the dataset has no val/test split, make a stratified 70/15/15 split."""
    tr = data["train"]; va = data["val"]; te = data["test"]
    if not te and not va:
        y = [l for _, l in tr]; tr, rest = train_test_split(tr, test_size=0.30, stratify=y, random_state=seed)
        va, te = train_test_split(rest, test_size=0.5, stratify=[l for _, l in rest], random_state=seed)
    elif not va:
        tr, va = train_test_split(tr, test_size=0.15, stratify=[l for _, l in tr], random_state=seed)
    elif not te:
        va, te = train_test_split(va, test_size=0.5, stratify=[l for _, l in va], random_state=seed)
    return tr, va, te
