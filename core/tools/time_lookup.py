"""Exact local time for an IANA timezone using the host timezone database."""
from datetime import datetime
import json
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def current_time(timezone: str = 'Asia/Shanghai') -> str:
    if not isinstance(timezone,str) or not 1<=len(timezone)<=80:
        raise ValueError('时区名称无效。')
    try:now=datetime.now(ZoneInfo(timezone))
    except ZoneInfoNotFoundError as exc:raise ValueError('未知 IANA 时区。') from exc
    return json.dumps({'timezone':timezone,'iso':now.isoformat(),'date':now.date().isoformat(),
        'time':now.strftime('%H:%M:%S'),'utc_offset':now.strftime('%z')},ensure_ascii=False)
