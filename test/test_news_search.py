from datetime import datetime,timezone
import json
import pytest
from core.tools.news_search import date_window,parse_feed
from core.gui.task_summary import format_summary
from core.security.multi_step_graph import parse_plan,UnsupportedGoalError


def test_yesterday_uses_shanghai_calendar_day():
    start,end=date_window('yesterday',datetime(2026,10,12,17,tzinfo=timezone.utc))
    assert start.isoformat()=='2026-10-12T00:00:00+08:00'
    assert end.isoformat()=='2026-10-13T00:00:00+08:00'


def test_feed_filters_exact_dates_invalid_times_and_unsafe_links():
    start,end=date_window('yesterday',datetime(2026,10,12,17,tzinfo=timezone.utc))
    def item(date,link):return f'<item><title>AI &amp; Science</title><link>{link}</link><pubDate>{date}</pubDate><source>Example</source></item>'
    raw=('<rss><channel>'+item('Sun, 11 Oct 2026 16:00:00 GMT','https://example.com/one')+
         item('Mon, 12 Oct 2026 15:59:59 GMT','https://example.com/two')+
         item('Mon, 12 Oct 2026 16:00:00 GMT','https://example.com/future')+
         item('Sun, 11 Oct 2026 15:59:59 GMT','https://example.com/old')+
         item('bad','https://example.com/bad')+
         item('Mon, 12 Oct 2026 14:00:00 GMT','javascript:alert(1)')+'</channel></rss>').encode()
    rows=parse_feed(raw,start,end,10)
    assert len(rows)==2 and rows[0]['url'].endswith('/two') and rows[0]['title']=='AI & Science'
    assert parse_feed(b'<rss><channel/></rss>',start,end,8)==[]
    with pytest.raises(ValueError):parse_feed(b'<!DOCTYPE rss><rss/>',start,end,8)


def test_summary_cites_only_observed_sources():
    evidence=[{'source':'Example','published_at':'2026-10-12','url':'https://example.com/news'}]
    assert 'https://example.com/news' in format_summary(json.dumps({'items':[{'text':'AI update','sources':[1]}]}),evidence)
    for refs in ([],[0],[2],[True]):
        with pytest.raises(ValueError):format_summary(json.dumps({'items':[{'text':'AI update','sources':refs}]}),evidence)


def test_unavailable_goal_has_distinct_error():
    with pytest.raises(UnsupportedGoalError):parse_plan('{"steps":[]}','unsupported')


def test_news_is_plannable_without_code():
    plan=parse_plan('{"steps":[{"tool":"news_search","arguments":{"query":"AI","period":"yesterday"}}]}','昨天AI新闻')
    assert plan[0]['tool']=='news_search'
    with pytest.raises(ValueError):parse_plan('{"steps":[{"tool":"news_search","arguments":{"query":"AI","period":"all"}}]}','AI新闻')
