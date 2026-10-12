"""Phase 5.12.2: fail-closed DAG metadata and dependency gates.

Current LangGraph executor is sequential. Dependencies are therefore validated
and persisted, not executed in parallel. No tool calls are performed here.
"""
from contextlib import closing
import json
import re
import sqlite3
from pathlib import Path

_REF = re.compile(r'\{\{step:([1-9][0-9]*):json:(?:/[^{}\s]*)?\}\}')
MAX_STEPS = 32


def dependencies(steps):
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('DAG step count out of bounds')
    graph = {}
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get('arguments'), dict):
            raise ValueError('Invalid step')
        explicit = step.get('depends_on', [])
        if not isinstance(explicit, list) or any(type(n) is not int for n in explicit):
            raise ValueError('depends_on must be a list of 1-based step numbers')
        code = step['arguments'].get('code', '') if step.get('tool') == 'run_python_code' else ''
        if not isinstance(code, str):
            raise ValueError('Invalid code argument')
        if '{{step:' in code and '{{step:' in _REF.sub('', code):
            raise ValueError('Malformed step reference')
        refs = {int(match.group(1)) for match in _REF.finditer(code)}
        deps = set(explicit) | refs
        if any(n <= 0 or n > len(steps) for n in deps):
            raise ValueError('Invalid dependency step')
        if index + 1 in deps:
            raise ValueError('Self dependency')
        # The existing checkpoint runner is serial and cannot reorder tasks.
        if any(n >= index + 1 for n in deps):
            raise ValueError('Forward dependency not supported by serial executor')
        graph[index + 1] = sorted(deps)
    return graph


def validate_acyclic(graph):
    visited, active = set(), set()
    def walk(node):
        if node in active:
            raise ValueError('Dependency cycle')
        if node in visited:
            return
        active.add(node)
        for dep in graph[node]:
            if dep not in graph:
                raise ValueError('Missing dependency')
            walk(dep)
        active.remove(node)
        visited.add(node)
    for node in graph:
        walk(node)
    return True


class DagStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('CREATE TABLE IF NOT EXISTS dag_plans (session TEXT NOT NULL, task TEXT NOT NULL, graph TEXT NOT NULL, PRIMARY KEY(session,task))')
            db.commit()

    def create(self, session, task, steps):
        graph = dependencies(steps)
        validate_acyclic(graph)
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('INSERT INTO dag_plans VALUES (?,?,?)', (session, task, json.dumps(graph)))
            db.commit()
        return graph

    def get(self, session, task):
        with closing(sqlite3.connect(self.path)) as db:
            row = db.execute('SELECT graph FROM dag_plans WHERE session=? AND task=?', (session, task)).fetchone()
        if row is None:
            raise KeyError('DAG metadata unavailable for this session/task')
        graph = {int(k): v for k, v in json.loads(row[0]).items()}
        validate_acyclic(graph)
        return graph

    def check(self, session, task, index, result_store):
        graph = self.get(session, task)
        number = index + 1
        if number not in graph:
            raise PermissionError('Current step missing from DAG')
        for dep in graph[number]:
            try:
                row = result_store.get(session, task, dep - 1)
            except (KeyError, ValueError) as exc:
                raise PermissionError(f'Dependency {dep} result missing') from exc
            if row['status'] != 'completed' or row['truncated']:
                raise PermissionError(f'Dependency {dep} is not a complete trusted result')
        return True
