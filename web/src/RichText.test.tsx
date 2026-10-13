import {expect,it} from 'vitest';
import {renderToStaticMarkup} from 'react-dom/server';
import {RichText,NewsSummary,safeLink} from './RichText';

it('renders tables and fenced code without running HTML or loading remote images',()=>{
  const html=renderToStaticMarkup(<RichText text={'|主题|说明|\n|---|---|\n|AI|学习|\n\n```python\nprint(42)\n```\n\n<script>alert(1)</script>\n\n![private](https://example.com/pixel)\n\n[bad](javascript:alert(1))'}/>);
  expect(html).toContain('<table>');expect(html).toContain('print(42)');
  expect(html).not.toContain('<script');expect(html).not.toContain('<img');expect(html).not.toContain('href="javascript:');
});
it('links news citations compactly without losing the original target',()=>{
  const html=renderToStaticMarkup(<NewsSummary text={'• 新闻条目\n\n  https://example.com/article?ref=1'}/>);
  expect(html).toContain('href="https://example.com/article?ref=1"');expect(html).toContain('查看报道');
  expect(html).toContain('noopener noreferrer');
});
it('blocks local and executable link schemes',()=>{
  for(const url of ['javascript:alert(1)','data:text/html,test','file:///D:/private','//tracker.example/'])expect(safeLink(url)).toBe('');
  expect(safeLink('https://example.com')).toBe('https://example.com');
});
