"""Bounded UTF-8 CSV reader. Cell contents are data, never formulas or code."""
import csv
import io
import json
from pathlib import Path


def extract_csv(csv_path: str) -> str:
    with Path(csv_path).open('rb') as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('CSV exceeds 1 MiB limit')
    text = raw.decode('utf-8-sig', errors='strict')
    reader = csv.reader(io.StringIO(text, newline=''), strict=True)
    columns = next(reader, [])
    if not columns or len(columns) > 100 or any(not c.strip() or len(c) > 128 for c in columns) or len(set(columns)) != len(columns):
        raise ValueError('CSV requires 1-100 unique nonempty column names')
    rows = []
    size = len(json.dumps(columns, ensure_ascii=False).encode('utf-8')) + 128
    for row in reader:
        if len(rows) >= 10000:
            raise ValueError('CSV exceeds 10000 row limit')
        if len(row) != len(columns):
            raise ValueError('CSV row width differs from header')
        record = dict(zip(columns, row))
        size += len(json.dumps(record, ensure_ascii=False).encode('utf-8')) + 2
        if size > 2000000:
            raise ValueError('CSV structured output exceeds 2 MB limit')
        rows.append(record)
    return json.dumps({'columns':columns, 'rows':rows, 'row_count':len(rows)}, ensure_ascii=False)
