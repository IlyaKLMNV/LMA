#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Загрузка URL → извлечение текста → (опционально) очистка.
Поддерживает легкую фильтрацию по языку (ru/en/auto).
Сохраняет сырой текст, а при флаге --raw-bytes-out — исходные байты ответа.
"""

import argparse, os, sys, json, time, hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse
import re

# Локальные импорты из соседней папки scripts
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

try:
    import httpx
except Exception:
    httpx = None

import clean_any  # pipeline_to_text / clean_text

UA = "Mozilla/5.0 (compatible; WhooshIngest/1.0; +https://whoosh-bike.ru)"


def is_url(s: str) -> bool:
    """Проверка, что передана http/https ссылка."""
    try:
        u = urlparse(s)
        return u.scheme in ("http", "https")
    except Exception:
        return False


def fetch_url(url: str, timeout=60, retries=3, backoff=1.7) -> bytes:
    """Получение байтов по URL с повторами и follow_redirects."""
    if httpx is None:
        raise RuntimeError("httpx не установлен. pip install httpx")
    last_exc = None
    for i in range(retries):
        try:
            with httpx.Client(follow_redirects=True, timeout=timeout, headers={"User-Agent": UA}) as client:
                r = client.get(url)
                r.raise_for_status()
                return r.content
        except Exception as e:
            last_exc = e
            time.sleep(backoff ** (i + 1))
    raise last_exc


def ensure_dir(path: str):
    """Создание директории для файла, если её нет."""
    d = os.path.dirname(os.path.abspath(path))
    if d and not os.path.exists(d):
        os.makedirs(d, exist_ok=True)


def derive_clean_out(out_path: str) -> str:
    """Автоматический путь для очищённого текста (/raw/ → /clean/ или .clean.txt)."""
    if re.search(r'[/\\]raw[/\\]', out_path):
        return re.sub(r'([/\\])raw([/\\])', r'\1clean\2', out_path)
    base, ext = os.path.splitext(out_path)
    return base + ".clean" + (ext or ".txt")


def write_text(path: str, text: str):
    """Запись текста в файл с финальным переводом строки."""
    ensure_dir(path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text if text.endswith("\n") else text + "\n")


def sha256_bytes(b: bytes) -> str:
    """Хэш от исходных байтов для аудита/кэша."""
    return hashlib.sha256(b).hexdigest()


def main():
    p = argparse.ArgumentParser(description="Fetch URL → text, optionally clean it")
    p.add_argument("url", help="Источник (URL)")
    p.add_argument("out", help="Путь, куда сохранить извлечённый текст")
    p.add_argument("--clean", action="store_true", help="Сразу прогнать через клинер")
    p.add_argument("--clean-out", help="Путь для сохранения очищенного текста (по умолчанию автомаппинг из --out)")
    p.add_argument("--keep-urls", action="store_true", help="Оставлять URL в тексте при чистке")
    p.add_argument("--min-keep-chars", type=int, default=25, help="Минимальная длина строки для сохранения")
    p.add_argument("--lang", choices=["auto", "ru", "en", "none"], default="none",
                   help="Фильтрация по языку извлечённого/очищенного текста")
    p.add_argument("--lang-threshold", type=float, default=0.7,
                   help="Порог доминирования алфавита в строке (0.5–0.9)")
    p.add_argument("--stats", action="store_true", help="Напечатать JSON-статистику в stdout")
    p.add_argument("--raw-bytes-out", help="Сохранить сырые байты ответа (html/pdf и т.п.)")
    args = p.parse_args()

    if not is_url(args.url):
        raise SystemExit("Ожидался URL. Для локальных файлов используйте отдельный скрипт или file://")

    # 1) скачиваем байты
    data = fetch_url(args.url)

    # 2) извлекаем сырой текст (html/pdf/text) с возможной дом-фильтрацией по языку
    txt = clean_any.pipeline_to_text(
        data,
        force_type=None,
        url_hint=args.url,
        keep_urls=args.keep_urls,
        prefer_lang=(args.lang if args.lang != "none" else None),
    )

    # 3) сохраняем сырой текст
    write_text(args.out, txt)

    # 4) опционально сохраняем сырые байты
    if args.raw_bytes_out:
        ensure_dir(args.raw_bytes_out)
        with open(args.raw_bytes_out, "wb") as f:
            f.write(data)

    result = {
        "source": args.url,
        "out": os.path.abspath(args.out),
        "raw_bytes_out": os.path.abspath(args.raw_bytes_out) if args.raw_bytes_out else None,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "sha256_bytes": sha256_bytes(data),
        "cleaned": None,
        "clean_stats": None,
    }

    # 5) при флаге clean — доп. очистка + языковой пост-фильтр
    if args.clean:
        clean_out = args.clean_out or derive_clean_out(args.out)
        cleaned, stats = clean_any.clean_text(
            txt,
            keep_urls=args.keep_urls,
            min_keep_chars=args.min_keep_chars,
            prefer_lang=(args.lang if args.lang != "none" else None),
            lang_threshold=args.lang_threshold,
        )
        write_text(clean_out, cleaned)
        result["cleaned"] = os.path.abspath(clean_out)
        result["clean_stats"] = stats

    if args.stats:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
