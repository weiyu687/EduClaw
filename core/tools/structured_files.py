"""Bounded UTF-8 readers and deterministic CSV profiling; never execute content."""
from decimal import Decimal, localcontext
import hashlib
import json
from pathlib import Path
import re

from core.tools.extract_csv import extract_csv

MAX_BYTES=1024*1024


def _read(path):
    with Path(path).open('rb') as stream:
        raw=stream.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise ValueError('File exceeds 1 MiB limit')
    text=raw.decode('utf-8-sig',errors='strict')
    if '\x00' in text: raise ValueError('NUL is not accepted in text input')
    return text,hashlib.sha256(raw).hexdigest()


def _constant(value):
    raise ValueError('Non-finite JSON numbers are not accepted')


def _pairs(items):
    out={}
    for key,value in items:
        if key in out: raise ValueError('Duplicate JSON object key')
        out[key]=value
    return out


def _json(text):
    import math
    value=json.loads(text,object_pairs_hook=_pairs,parse_constant=_constant)
    pending=[(value,0)];count=0
    while pending:
        item,depth=pending.pop();count+=1
        if count>50000 or depth>32: raise ValueError('JSON exceeds depth or node limit')
        if isinstance(item,float) and not math.isfinite(item): raise ValueError('JSON numeric overflow')
        if isinstance(item,dict): pending.extend((v,depth+1) for v in item.values())
        elif isinstance(item,list): pending.extend((v,depth+1) for v in item)
    return value


def _output(value):
    encoded=json.dumps(value,ensure_ascii=False,allow_nan=False)
    if len(encoded.encode('utf-8'))>2000000: raise ValueError('Structured result exceeds 2 MB limit')
    return encoded


def extract_text(text_path: str) -> str:
    text,digest=_read(text_path)
    lines=text.splitlines()
    if len(lines)>10000: raise ValueError('Text exceeds 10000 line limit')
    return _output({'text':text,'line_count':len(lines),'encoding':'utf-8','sha256':digest})


def extract_json(json_path: str) -> str:
    text,digest=_read(json_path)
    value=_json(text)
    if not isinstance(value,(dict,list)): raise ValueError('JSON root must be an object or array')
    return _output({'data':value,'root_type':'object' if isinstance(value,dict) else 'array','sha256':digest})


def extract_jsonl(jsonl_path: str) -> str:
    text,digest=_read(jsonl_path)
    records=[]
    for line in text.splitlines():
        if not line.strip(): continue
        if len(line.encode('utf-8'))>65536: raise ValueError('JSONL line exceeds 64 KiB limit')
        if len(records)>=10000: raise ValueError('JSONL exceeds 10000 record limit')
        value=_json(line)
        if not isinstance(value,dict): raise ValueError('Each JSONL record must be an object')
        records.append(value)
    return _output({'records':records,'record_count':len(records),'sha256':digest})


def profile_csv(csv_path: str) -> str:
    """Read a CSV once; profile empty cells, exact duplicate rows and decimal values."""
    data=json.loads(extract_csv(csv_path))
    columns,rows=data['columns'],data['rows']
    missing={column:sum(not row[column].strip() for row in rows) for column in columns}
    distinct={tuple(row[column] for column in columns) for row in rows}
    numeric={}
    with localcontext() as context:
        context.prec=80
        for column in columns:
            values=[]
            for row in rows:
                raw=row[column].strip()
                if len(raw)<=64 and re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)',raw):
                    values.append(Decimal(raw))
            if values:
                total=sum(values,Decimal(0))
                numeric[column]={'count':len(values),'min':str(min(values)),'max':str(max(values)),
                                 'sum':str(total),'mean':str(total/len(values))}
    return _output({'row_count':len(rows),'columns':columns,'missing':missing,
                    'duplicate_rows':len(rows)-len(distinct),'numeric':numeric})
