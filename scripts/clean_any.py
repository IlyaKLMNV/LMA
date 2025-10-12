# scripts/clean_any.py
# -*- coding: utf-8 -*-
"""
Универсальный пайплайн извлечения и очистки текста из HTML/PDF/Plain:
- pipeline_to_text(bytes, force_type=None, url_hint=None, keep_urls=False, prefer_lang=None) -> str
- pdf_to_text_bytes(pdf_bytes) -> str
- clean_text(text, keep_urls=False, min_keep_chars=25, prefer_lang=None, lang_threshold=0.7) -> (str, stats: dict)

Дополнительно:
- Лёгкая фильтрация по языку (ru/en/auto) на уровне строк.
- Аккуратное склеивание переносов по дефису.
- Минимальные эвристики для извлечения основного текста из HTML.

Зависимости (желательны, но есть фолбэки):
    beautifulsoup4, lxml, pdfminer.six, PyPDF2, readability-lxml (опционально)
"""

from __future__ import annotations
import io, re, sys, html
from typing import Optional, Tuple, Dict

# --- опциональные зависимости (импортируем бережно) ---
try:
    from bs4 import BeautifulSoup, Tag  # type: ignore
except Exception:
    BeautifulSoup = None  # type: ignore
    Tag = None  # type: ignore

try:
    from pdfminer_high_level import extract_text as pdfminer_extract_text  # type: ignore
except Exception:
    # совместимость с pdfminer.six
    try:
        from pdfminer.high_level import extract_text as pdfminer_extract_text  # type: ignore
    except Exception:
        pdfminer_extract_text = None  # type: ignore

try:
    import PyPDF2  # type: ignore
except Exception:
    PyPDF2 = None  # type: ignore

try:
    from readability import Document  # readability-lxml (необязательно)
except Exception:
    Document = None  # type: ignore


# ------------------ ВСПОМОГАТЕЛЬНОЕ ------------------

NBSP = u"\u00A0"
_SOFT_HYPHEN = u"\u00AD"

# Регэкспы для приблизительного определения алфавита в тексте
_CYRIL = re.compile(r"[А-Яа-яЁё]")
_LATIN = re.compile(r"[A-Za-z]")


def _ensure_str(s: bytes, fallback="utf-8") -> str:
    """Безопасно декодирует байты в строку с несколькими кодировочными попытками."""
    if isinstance(s, str):
        return s
    try:
        return s.decode("utf-8")
    except Exception:
        pass
    try:
        return s.decode(fallback, errors="replace")
    except Exception:
        return s.decode("latin-1", errors="replace")


def _looks_like_html(txt: str) -> bool:
    """Быстрая эвристика, похожа ли строка на HTML."""
    t = txt[:2000].lower()
    return ("<html" in t) or ("<!doctype html" in t) or ("</div>" in t) or ("</p>" in t)


def _looks_like_pdf(b: bytes) -> bool:
    """Проверка сигнатуры PDF."""
    return b[:8].startswith(b"%PDF")


def _collapse_spaces(s: str) -> str:
    """Схлопывает лишние пробелы и пустые строки."""
    s = s.replace(NBSP, " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def _script_counts(s: str) -> Tuple[int, int]:
    """Подсчёт вхождений кириллицы и латиницы в строке."""
    return len(_CYRIL.findall(s)), len(_LATIN.findall(s))


def _classify_line_lang(line: str, threshold: float = 0.7) -> str:
    """
    Классификация строки по доминирующему алфавиту:
    - 'ru' / 'en' / 'mixed' / 'neutral'
    """
    c, l = _script_counts(line)
    tot = c + l
    if tot == 0:
        return "neutral"
    rc, rl = c / tot, l / tot
    if rc >= threshold:
        return "ru"
    if rl >= threshold:
        return "en"
    return "mixed"


def _unhyphenate(text: str) -> str:
    """
    Склейка переносов по дефису и удаление soft hyphen.
    Оставляет перевод строки, убирает только «-\\n» внутри слова.
    """
    t = text.replace(_SOFT_HYPHEN, "")
    t = re.sub(r"([A-Za-zА-Яа-яЁё]{2,})-\n([A-Za-zА-Яа-яЁё]{2,})", r"\1\2\n", t)
    return t


def _filter_text_by_lang(text: str,
                         prefer: Optional[str] = "auto",
                         threshold: float = 0.7,
                         keep_neutral: bool = True,
                         keep_short_mixed: bool = True,
                         short_len: int = 60) -> Tuple[str, Dict]:
    """
    Фильтрация строк текста по предпочитаемому языку.
      - prefer: 'ru'|'en'|'auto'|None
      - threshold: порог доминирования алфавита (0..1)
    Возвращает (отфильтрованный_текст, статистика_фильтра).
    """
    lines = text.split("\n")
    auto_choice = None

    if prefer in (None, "", "auto"):
        c_tot = l_tot = 0
        for ln in lines:
            c, l = _script_counts(ln)
            c_tot += c
            l_tot += l
        prefer = "ru" if c_tot >= l_tot else "en"
        auto_choice = prefer

    kept: list[str] = []
    stats = {
        "lang_prefer": prefer,
        "lang_auto_choice": auto_choice,
        "lines_in": len(lines),
        "lines_kept": 0,
        "neutral_kept": 0,
        "mixed_kept": 0,
        "lines_filtered": 0,
        "threshold": threshold,
    }

    for ln in lines:
        tag = _classify_line_lang(ln, threshold)
        keep = False
        if tag == prefer:
            keep = True
        elif tag == "neutral" and keep_neutral:
            keep = True
            stats["neutral_kept"] += 1
        elif tag == "mixed" and keep_short_mixed and len(ln) <= short_len:
            keep = True
            stats["mixed_kept"] += 1

        if keep:
            kept.append(ln)
        else:
            stats["lines_filtered"] += 1

    stats["lines_kept"] = len(kept)
    return "\n".join(kept), stats


# ------------------ ИЗВЛЕЧЕНИЕ ИЗ PDF ------------------

def pdf_to_text_bytes(pdf_bytes: bytes) -> str:
    """
    Извлекает текст из PDF-байтов. Порядок попыток:
      1) pdfminer.six (желательно)
      2) PyPDF2 (фолбэк)
      3) пустая строка (крайний случай)
    """
    if pdfminer_extract_text is not None:
        try:
            return pdfminer_extract_text(io.BytesIO(pdf_bytes)) or ""
        except Exception:
            pass

    if PyPDF2 is not None:
        try:
            reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
            out = []
            for page in reader.pages:
                try:
                    out.append(page.extract_text() or "")
                except Exception:
                    out.append("")
            return "\n".join(out)
        except Exception:
            pass

    return ""


# ------------------ ИЗВЛЕЧЕНИЕ ИЗ HTML ------------------

_HTML_STRIP_SELECTORS = [
    # Теги, которые почти всегда шум
    "script", "style", "noscript", "template", "svg", "iframe"
]

def _bs4_main_text(s: str,
                   url_hint: str | None = None,
                   keep_urls: bool = False,
                   prefer_lang: Optional[str] = None) -> str:
    """
    Извлекает основной текст из HTML.
    - Если обнаружены явные языковые метки, при prefer_lang ('ru'/'en') вырезает блоки «другого» языка.
    - Далее выбирает лучший по эвристике блок с контентом.
    """
    if BeautifulSoup is None:
        # Фолбэк без bs4: грубое удаление тегов (лучше поставить bs4+lxml)
        txt = re.sub(r"<[^>]+>", " ", s or "")
        txt = html.unescape(txt)
        txt = re.sub(r"\s+", " ", txt)
        return txt.strip()

    soup = BeautifulSoup(s or "", "lxml")

    # Явная фильтрация по меткам языка (если присутствуют)
    if prefer_lang in ("ru", "en"):
        other = "ru" if prefer_lang == "en" else "en"
        has_markers = soup.find(attrs={"lang": True}) or soup.find(class_=re.compile(r"\blang[-_](ru|en)\b", re.I))
        if has_markers:
            for node in list(soup.find_all(True)):
                try:
                    lang_attr = (node.get("lang") or node.get("xml:lang") or node.get("data-lang") or "").lower()
                    classes = " ".join(node.get("class") or []).lower()
                    ident = (node.get("id") or "").lower()
                    hay = " ".join([lang_attr, classes, ident])
                    if re.search(rf"\b(lang[-_])?{other}\b", hay):
                        node.decompose()
                except Exception:
                    # В сомнительных случаях не трогаем
                    pass

    # Удаление технических тегов
    for t in soup(_HTML_STRIP_SELECTORS):
        try:
            t.decompose()
        except Exception:
            pass

    # Рабочее тело документа
    body = soup.body or soup

    # Перебор контейнеров в поиске самого «текстового» кандидата
    nodes = []
    if isinstance(body, Tag):
        nodes.append(body)
    nodes.extend(body.find_all(True))

    best_txt = ""
    best_score = -1.0

    for node in nodes:
        if not isinstance(node, Tag):
            continue

        hay = " ".join(filter(None, [
            node.name or "",
            " ".join((node.get("class") or [])),
            (node.get("id") or ""),
            (node.get("role") or "")
        ])).lower()

        # Пропускаем заведомо навигационный/служебный хром
        if any(k in hay for k in [
            "header", "footer", "nav", "menu", "breadcrumb", "breadcrumbs", "aside", "sidebar",
            "subscribe", "subscription", "cookie", "consent", "captcha", "popup", "modal",
            "share", "social", "banner", "tilda", "tmenu", "t396", "t754", "t706"
        ]):
            continue

        txt = node.get_text("\n", strip=True)
        if len(txt) < 200:
            continue

        link_len = 0
        for a in node.find_all("a"):
            try:
                link_len += len(a.get_text(" ", strip=True))
            except Exception:
                pass
        link_density = link_len / max(1, len(txt))

        weight = 0
        if any(k in hay for k in [
            "article", "main", "content", "post", "entry", "text", "page", "document",
            "terms", "policy", "оферта", "условия"
        ]):
            weight += 2

        score = len(txt) * (1 - link_density) + weight * 1000
        if score > best_score:
            best_score = score
            best_txt = txt

    # Фолбэк, если ничего подходящего не нашли
    if not best_txt:
        best_txt = soup.get_text("\n", strip=True)

    # Нормализация переводов строк
    best_txt = re.sub(r"[ \t]*\n[ \t]*", "\n", best_txt)
    best_txt = re.sub(r"\n{3,}", "\n\n", best_txt)
    return best_txt


# ------------------ ПАЙПЛАЙН ДЕТЕКТА + ИЗВЛЕЧЕНИЯ ------------------

def pipeline_to_text(data: bytes,
                     force_type: Optional[str] = None,
                     url_hint: Optional[str] = None,
                     keep_urls: bool = False,
                     prefer_lang: Optional[str] = None) -> str:
    """
    Определяет тип источника и извлекает «сырой» текст.
      - force_type: "pdf"|"html"|"text"|None
      - prefer_lang: пробрасывается в HTML-извлечение для явной фильтрации DOM (если есть метки)
    """
    ftype = (force_type or "").lower().strip()

    # Явное указание
    if ftype == "pdf":
        return pdf_to_text_bytes(data)
    if ftype == "html":
        return _bs4_main_text(_ensure_str(data), url_hint, keep_urls, prefer_lang=prefer_lang)
    if ftype == "text":
        return _collapse_spaces(_ensure_str(data))

    # Автодетект
    if isinstance(data, (bytes, bytearray)) and _looks_like_pdf(data):
        return pdf_to_text_bytes(data)

    s = _ensure_str(data)
    if _looks_like_html(s):
        return _bs4_main_text(s, url_hint, keep_urls, prefer_lang=prefer_lang)

    # Текст как есть
    return _collapse_spaces(s)


# ------------------ ОЧИСТКА И НОРМАЛИЗАЦИЯ ------------------

_BULLET = r"[•·◦▪▫●■□–\-‒—•◆]"

# Типичные «служебные» строки (шапки/футеры/хлебные крошки и т.п.)
_LINE_NOISE_PAT = re.compile(
    r"^(ok|copyright|all rights reserved|©|\s*навигац|меню|faq|подписк|промокод|"
    r"инвестор|ваканси|магазин|парковк|контакт|privacy|cookie|политика конфиденциальности)\b",
    re.IGNORECASE
)

def _normalize_punctuation(line: str) -> str:
    """Единообразие тире/кавычек и лишних пробелов."""
    line = line.replace("—", "-").replace("–", "-")
    line = line.replace("“", "\"").replace("”", "\"").replace("«", "\"").replace("»", "\"").replace("’", "'")
    line = line.replace(NBSP, " ")
    line = re.sub(r"[ \t]+", " ", line)
    return line.strip()


def clean_text(text: str,
               keep_urls: bool = False,
               min_keep_chars: int = 25,
               prefer_lang: Optional[str] = None,
               lang_threshold: float = 0.7) -> Tuple[str, Dict]:
    """
    Очистка текста:
      - опционально фильтрация по языку (ru/en/auto)
      - склейка переносов по дефису
      - удаление служебных строк и повтора подряд
      - нормализация пробелов/пунктуации
    Возвращает (очищенный_текст, статистика).
    """
    original = text or ""

    # Нормализация переводов строк и HTML-сущностей
    t = original.replace("\r\n", "\n").replace("\r", "\n")
    t = html.unescape(t)

    # Склейка переносов по дефису
    t = _unhyphenate(t)

    # Предварительная фильтрация по языку (если задано)
    lang_stats = None
    if prefer_lang in ("ru", "en", "auto"):
        t, lang_stats = _filter_text_by_lang(
            t, prefer=prefer_lang, threshold=lang_threshold,
            keep_neutral=True, keep_short_mixed=True, short_len=60
        )

    raw_lines = t.split("\n")
    kept_lines: list[str] = []
    removed = 0
    dedup_removed = 0
    prev = None

    for raw in raw_lines:
        line = raw.strip()
        if not line:
            # сохраняем пустую строку как разделитель, но не дублируем
            if kept_lines and kept_lines[-1] == "":
                continue
            kept_lines.append("")
            continue

        # Лёгкая нормализация
        line = _normalize_punctuation(line)

        # Удаление явных «служебных» строк
        if _LINE_NOISE_PAT.search(line):
            removed += 1
            continue

        # Фильтр ссылочных строк на соцсети/платформы
        if re.search(r"(vk\.com|instagram\.com|facebook\.com|twitter\.com|t\.me|youtube\.com|xn--)", line, re.I):
            if not keep_urls or len(line) < min_keep_chars:
                removed += 1
                continue

        # Изолированные маркеры/пункты
        if re.fullmatch(fr"\s*({_BULLET}|\*|\#|\d+\.|\d+\))\s*", line):
            removed += 1
            continue

        # Очень короткие строки
        if len(line) < min_keep_chars:
            # Оставляем ненумерованные мини-заголовки без URL
            if not re.search(r"https?://|www\.", line, re.I) and re.search(r"[А-ЯA-Zа-яa-z]", line):
                kept_lines.append(line)
            else:
                removed += 1
            continue

        # Удаление дублей подряд
        if prev and prev == line:
            dedup_removed += 1
            continue

        kept_lines.append(line)
        prev = line

    # Схлопывание лишних пустых строк
    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()

    stats: Dict = {
        "lines_in": len(raw_lines),
        "lines_out": len(cleaned.split("\n")) if cleaned else 0,
        "chars_in": len(original),
        "chars_out": len(cleaned),
        "removed_noise": removed,
        "removed_duplicates": dedup_removed,
        "min_keep_chars": min_keep_chars,
        "keep_urls": keep_urls,
    }
    if lang_stats:
        stats["lang_filter"] = lang_stats
    return cleaned, stats


# ------------------ CLI ------------------

if __name__ == "__main__":
    import argparse, json, pathlib

    p = argparse.ArgumentParser(description="Universal cleaner")
    p.add_argument("--in", dest="in_path", required=True, help="Входной файл (bytes/текст)")
    p.add_argument("--out", dest="out_path", required=True, help="Куда сохранить очищенный текст")
    p.add_argument("--force-type", choices=["pdf", "html", "text"], help="Жёстко указать тип источника")
    p.add_argument("--keep-urls", action="store_true", help="Сохранять URL в тексте")
    p.add_argument("--min-keep-chars", type=int, default=25)
    p.add_argument("--lang", choices=["auto", "ru", "en", "none"], default="none",
                   help="Фильтрация по языку: auto/ru/en (none = без фильтра)")
    p.add_argument("--lang-threshold", type=float, default=0.7,
                   help="Порог доминирования алфавита в строке (0.5–0.9)")
    p.add_argument("--stats", action="store_true")
    args = p.parse_args()

    data = pathlib.Path(args.in_path).read_bytes()
    raw_txt = pipeline_to_text(
        data,
        force_type=args.force_type,
        url_hint=None,
        keep_urls=args.keep_urls,
        prefer_lang=(args.lang if args.lang != "none" else None),
    )
    cleaned, st = clean_text(
        raw_txt,
        keep_urls=args.keep_urls,
        min_keep_chars=args.min_keep_chars,
        prefer_lang=(args.lang if args.lang != "none" else None),
        lang_threshold=args.lang_threshold,
    )

    pathlib.Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(args.out_path).write_text(
        cleaned + ("\n" if not cleaned.endswith("\n") else ""), encoding="utf-8"
    )
    if args.stats:
        print(json.dumps(st, ensure_ascii=False, indent=2))
