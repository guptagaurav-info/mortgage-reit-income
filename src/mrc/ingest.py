"""Download the three public source files and check pinned checksums (python -m mrc.ingest)."""
import hashlib, os, urllib.request, yaml
if __name__ == "__main__":
    cfg = yaml.safe_load(open("configs/default.yaml")); os.makedirs("data/raw", exist_ok=True)
    for f, s in cfg["sources"].items():
        p = "data/raw/" + f
        if not os.path.exists(p):
            urllib.request.urlretrieve(s["url"], p)
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 24), b""):
                h.update(c)
        print(f, "OK" if h.hexdigest() == s["sha256"] else "MISMATCH (source updated; results may differ)")
