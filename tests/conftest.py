import base64
import hashlib
import sys
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def make_wheel(directory: Path, name: str, version: str, body: str) -> Path:
    """Build a minimal pure-python wheel so isolated-venv tests need no network."""
    directory.mkdir(parents=True, exist_ok=True)
    dist = f"{name}-{version}.dist-info"
    files = {f"{name}.py": body,
             f"{dist}/METADATA": f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
             f"{dist}/WHEEL": "Wheel-Version: 1.0\nGenerator: test\nRoot-Is-Purelib: true\nTag: py3-none-any\n"}
    rec = []
    for k, v in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
        rec.append(f"{k},sha256={digest},{len(v.encode())}")
    rec.append(f"{dist}/RECORD,,")
    files[f"{dist}/RECORD"] = "\n".join(rec) + "\n"
    out = directory / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(out, "w") as z:
        for k, v in files.items():
            z.writestr(k, v)
    return out


@pytest.fixture
def wheelhouse(tmp_path):
    wh = tmp_path / "wheelhouse"
    make_wheel(wh, "demo_dep", "1.0", "VERSION = '1.0'\n")
    make_wheel(wh, "demo_dep", "2.0", "VERSION = '2.0'\n")
    return wh


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path
