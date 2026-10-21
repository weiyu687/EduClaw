"""Readable CLI view of the same persisted step input and output as the GUI."""
import json

from core.security.step_status import LABELS


def render_flow(detail):
    lines=[f"任务 {detail['number']} · {detail['goal']}",
           f"进度 {detail['completed']}/{detail['total']} · 状态 {detail['status']}"]
    by_step={row['step']:row for row in detail['results']}
    for step in detail['steps']:
        row=by_step.get(step['number'])
        status=step['status']
        if row and (not row['intact'] or row['truncated'] or row['status']!='completed'):
            label='结果需核查'
        elif status=='completed' and not row:
            label='缺少结果'
        else:label=LABELS.get(status,status)
        lines.extend(['',f"{step['number']:02d}  {step['tool']} · {label}",
                      '依赖：'+('、'.join(str(value) for value in step['dependencies']) if step['dependencies'] else '无'),
                      '输入：'+json.dumps(step['arguments'],ensure_ascii=False,indent=2)])
        if row:
            lines.append('输出：'+row['summary'][:12000])
            lines.append('证据：'+('校验通过' if row['intact'] and not row['truncated'] else '不完整或校验未通过')+
                         ' · SHA256 '+row['digest'])
        else:lines.append('输出：尚未保存')
    return '\n'.join(lines)
