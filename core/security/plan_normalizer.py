"""Phase 5.12.2a: normalize legacy planner references before checkpoint creation.

Only an AST Name load of ``previous_result`` is accepted as an implicit reference.
It is replaced with the Phase 5.12.1 immutable JSON result syntax, never
with an ambient Python variable. Unknown implicit names are not guessed.
"""
import ast
import io
import tokenize


def normalize_plan(steps):
    if not isinstance(steps, list):
        raise ValueError('Plan must be a list')
    normalized = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict) or not isinstance(step.get('arguments'), dict):
            raise ValueError('Invalid plan step')
        new_step = {**step, 'arguments': dict(step['arguments'])}
        if new_step.get('tool') == 'run_python_code':
            code = new_step['arguments'].get('code')
            if not isinstance(code, str):
                raise ValueError('Python code must be text')
            try:
                tree = ast.parse(code)
            except SyntaxError as exc:
                # Phase 5.12.1 {{step:...}} placeholders are not Python syntax.
                if '{{step:' in code and 'previous_result' not in code:
                    normalized.append(new_step)
                    continue
                raise ValueError('Invalid Python plan code') from exc
            implicit_loads = [n for n in ast.walk(tree) if isinstance(n, ast.Name)
                              and n.id == 'previous_result' and isinstance(n.ctx, ast.Load)]
            if implicit_loads:
                if index == 0:
                    raise ValueError('First step cannot use previous_result')
                if any(isinstance(n, ast.Name) and n.id == 'previous_result'
                       and not isinstance(n.ctx, ast.Load) for n in ast.walk(tree)):
                    raise ValueError('Ambiguous previous_result assignment')
                # Tokenize to avoid rewriting comments and string literals.
                tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
                tokens = [tokenize.TokenInfo(t.type, '{{step:%d:json:}}' % index if
                          t.type == tokenize.NAME and t.string == 'previous_result' else t.string,
                          t.start, t.end, t.line) for t in tokens]
                code = tokenize.untokenize(tokens)
                new_step['arguments']['code'] = code
                deps = new_step.get('depends_on', [])
                if not isinstance(deps, list):
                    raise ValueError('Invalid depends_on')
                new_step['depends_on'] = sorted(set(deps) | {index})
        normalized.append(new_step)
    return normalized
