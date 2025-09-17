# File readers for common formats.

from pathlib import Path
from typing import Any
from fastapi import HTTPException

# PDF
from pypdf import PdfReader
# DOCX
import docx  # python-docx
# HTML/MD
from bs4 import BeautifulSoup
import html2text
# CSV/TSV
import pandas as pd

def normalize_text(s: str) -> str:
    return "\n".join(line.strip() for line in s.splitlines()).strip()

def read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")

def read_md(path: Path) -> str:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return html2text.html2text(txt)

def read_html(path: Path) -> str:
    html = path.read_text(encoding="utf-8", errors="ignore")
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n")

def read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n".join(pages)

def read_docx(path: Path) -> str:
    d = docx.Document(str(path))
    return "\n".join([p.text for p in d.paragraphs if p.text])

def read_csv(path: Path) -> str:
    df = pd.read_csv(path, dtype=str, encoding="utf-8", on_bad_lines="skip")
    lines = [", ".join(map(str, row.dropna().tolist())) for _, row in df.iterrows()]
    return "\n".join(lines)

def load_file_to_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return read_txt(path)
    if suffix in (".md", ".markdown"):
        return read_md(path)
    if suffix in (".html", ".htm"):
        return read_html(path)
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix == ".docx":
        return read_docx(path)
    if suffix in (".csv", ".tsv"):
        return read_csv(path)
    try:
        return read_txt(path)
    except Exception:
        raise HTTPException(400, f"Unsupported file type: {suffix}")
