"""Bounded document ingestion and stable, quotable source units."""
import csv
import hashlib
import io
import math
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile


class MaterialError(ValueError):
    pass


def identity(value):
    return hashlib.sha256(value.encode()).hexdigest()[:12]


def normalized(value):
    return re.sub(r"\s+", " ", str(value)).strip()


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (TypeError, ValueError):
        return None


def ingest(name, data):
    name = Path(name).name[:150]
    if not name or len(data) > 4_000_000:
        raise MaterialError("Each material needs a filename and must be under 4 MB.")
    suffix = Path(name).suffix.lower()
    if suffix == ".pdf":
        if not shutil.which("pdftotext"):
            raise MaterialError("PDF import needs pdftotext. Export the document as text instead.")
        with tempfile.TemporaryDirectory(prefix="presenter-pdf-") as folder:
            p = Path(folder) / "source.pdf"
            p.write_bytes(data)
            r = subprocess.run(["pdftotext", "-layout", str(p), "-"], capture_output=True, timeout=20)
            if r.returncode:
                raise MaterialError("PDF could not be read. Scanned PDFs need OCR first.")
            text = r.stdout.decode("utf-8")
    elif suffix == ".docx":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as doc:
                info = doc.getinfo("word/document.xml")
                if info.file_size > 5_000_000:
                    raise MaterialError("Word document text is too large.")
                root = ET.fromstring(doc.read(info))
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
                text = "\n".join("".join(p.itertext()) for p in root.findall(".//w:p", ns))
        except (zipfile.BadZipFile, KeyError, ET.ParseError):
            raise MaterialError("This is not a readable Word document.") from None
    elif suffix in {".txt", ".md", ".csv", ".tsv"}:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise MaterialError("Text and CSV files must use UTF-8 encoding.") from None
    else:
        raise MaterialError("Use TXT, Markdown, CSV, TSV, PDF or DOCX files.")
    if not text.strip() or len(text) > 100_000:
        raise MaterialError("Material must contain readable text, up to 100,000 characters per file.")
    source_id = "src_" + hashlib.sha256(data).hexdigest()[:12]
    units, heading = [], name
    for block in re.split(r"\n\s*\n", text.replace("\r\n", "\n")):
        block = block.strip()
        if not block:
            continue
        lines = block.splitlines()
        if lines[0].startswith("#"):
            heading = lines[0].lstrip("# ").strip()[:100]
            block = "\n".join(lines[1:]).strip()
            if not block:
                continue
        # Bound quotes without discarding source material.
        for offset in range(0, len(block), 1600):
            chunk = block[offset:offset + 1600]
            units.append({"id": source_id + "_" + str(len(units) + 1), "heading": heading,
                          "text": chunk, "source_id": source_id, "source_name": name})
    dataset = None
    if suffix in {".csv", ".tsv"}:
        table = list(csv.reader(io.StringIO(text), delimiter="\t" if suffix == ".tsv" else ","))
        if len(table) < 2 or len(table) > 1001 or not table[0] or len(table[0]) > 20:
            raise MaterialError("CSV needs a header and 1–1,000 rows, with at most 20 columns.")
        columns = [c.strip() for c in table[0]]
        if len(set(columns)) != len(columns) or not all(columns):
            raise MaterialError("CSV column names must be nonempty and unique.")
        rows = [dict(zip(columns, row)) for row in table[1:] if any(row)]
        if not rows:
            raise MaterialError("CSV needs at least one nonempty data row.")
        if any(len(row) != len(columns) for row in table[1:] if any(row)):
            raise MaterialError("CSV rows must have the same number of columns as the header.")
        numeric = [c for c in columns if all(number(row[c]) is not None for row in rows)]
        dataset = {"id": source_id, "name": name, "columns": columns, "numeric_columns": numeric, "rows": rows}
    return {"id": source_id, "name": name, "sha256": hashlib.sha256(data).hexdigest(),
            "characters": len(text), "units": units, "dataset": dataset}


def chart_data(dataset, x, y):
    if x not in dataset["columns"] or y not in dataset["numeric_columns"]:
        raise MaterialError("Chart columns must exist and the value column must be numeric.")
    return [{"label": str(row[x])[:100], "value": number(row[y])} for row in dataset["rows"][:32]]
