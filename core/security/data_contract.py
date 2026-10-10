"""Phase 5.12.2b: fail-closed dependency contracts for the serial multi runner."""
import ast
import re
from core.security.dag_dependencies import dependencies
from core.security.step_references import REF

LEGACY = ('previous_result', 'PREVIOUS_STEP_OUTPUT')
_PDF_LENGTH = re.compile(r'(?:总页数|页数|total pages)', re.I)
_LENGTH = re.compile(r'(?:文本长度|字符数|text length|lengths)', re.I)
_DEPENDENT = re.compile(r'(?:依赖|第一步.*结果|上一步.*结果|前一步.*结果|previous step|depends on)', re.I)


def _parse_template(code):
    """Parse Python with references replaced by inert integer literals."""
    if '{{step:' in REF.sub('', code):
        raise ValueError('Malformed step reference')
    masked = REF.sub('0', code)
    try:
        return ast.parse(masked)
    except SyntaxError as exc:
        raise ValueError(f'Python code syntax invalid: {exc.msg} (line {exc.lineno})') from exc


def _undefined_legacy(tree):
    return {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load) and node.id in LEGACY}


def prepare_plan(goal, steps, *, legacy_recipe=True):
    """Enforce explicit result references and syntactic validity before checkpoint creation.

    Narrow deterministic recipe is used only for PDF page-count/text-length tasks.
    For all other dependent tasks, malformed or unbound code is rejected, not guessed.
    """
    if not isinstance(steps, list) or not steps:
        raise ValueError('Plan is empty')
    out = []
    for i, original in enumerate(steps):
        if not isinstance(original, dict) or not isinstance(original.get('arguments'), dict):
            raise ValueError('Invalid step')
        step = {**original, 'arguments': dict(original['arguments'])}
        if step.get('tool') == 'run_python_code':
            code = step['arguments'].get('code')
            if not isinstance(code, str) or not code.strip():
                raise ValueError('Empty Python code')
            # A narrow, auditable recipe replaces unreliable LLM-generated code
            # only for the precise PDF page-count and page-text-length operation.
            recipe = (legacy_recipe and i == 1 and len(steps) == 2 and
                      steps[0].get('tool') == 'extract_pdf' and
                      _PDF_LENGTH.search(goal) and _LENGTH.search(goal) and
                      _DEPENDENT.search(goal))
            if recipe:
                code = ("data = {{step:1:json:}}\n"
                        "if not isinstance(data, dict) or not isinstance(data.get('pages'), list):\n"
                        "    raise ValueError('PDF result missing pages list')\n"
                        "pages = data['pages']\n"
                        "print('PDF 总页数:', len(pages))\n"
                        "for index, page in enumerate(pages, 1):\n"
                        "    if not isinstance(page, dict) or not isinstance(page.get('text'), str):\n"
                        "        raise ValueError('Invalid page text')\n"
                        "    print(f'第 {index} 页文本长度: {len(page[\"text\"])}')\n")
            else:
                # Known ambient names are never trusted as injected globals.
                tree = None
                try:
                    tree = _parse_template(code)
                except ValueError:
                    # Malformed generated code must be rejected before any MCP call.
                    raise
                names = _undefined_legacy(tree)
                if names:
                    if i == 0:
                        raise ValueError('First step cannot refer to prior result')
                    if len(names) != 1 or any(isinstance(n, ast.Name) and n.id in LEGACY and
                                              not isinstance(n.ctx, ast.Load) for n in ast.walk(tree)):
                        raise ValueError('Ambiguous legacy result variable')
                    # Only standalone identifier tokens are replaced, not comments/strings.
                    import io, tokenize
                    tokens = list(tokenize.generate_tokens(io.StringIO(code).readline))
                    tokens = [t._replace(string='{{step:%d:json:}}' % i)
                              if t.type == tokenize.NAME and t.string in names else t for t in tokens]
                    code = tokenize.untokenize(tokens)
            tree = _parse_template(code)
            if _undefined_legacy(tree):
                raise ValueError('Unbound result variable')
            refs = {int(m.group(1)) for m in REF.finditer(code)}
            if any(n > i for n in refs):
                raise ValueError('Reference must target earlier step')
            # Fail closed: a declared dependency must actually be consumed.
            declared = step.get('depends_on', [])
            if not isinstance(declared, list):
                raise ValueError('Invalid depends_on')
            if declared and not set(declared).issubset(refs):
                raise ValueError('Declared Python data dependency is not referenced')
            if i and _DEPENDENT.search(goal) and not refs:
                raise ValueError('Dependent Python step must use explicit result reference')
            step['arguments']['code'] = code
            if refs:
                step['depends_on'] = sorted(set(declared) | refs)
        out.append(step)
    graph = dependencies(out)
    # The planner must not silently discard a user-mandated data dependency.
    if len(out) > 1 and _DEPENDENT.search(goal) and out[-1]['tool'] == 'run_python_code' and not graph[len(out)]:
        raise ValueError('Missing required final-step data dependency')
    return out


def validate_resolved_code(code):
    if '{{step:' in code:
        raise ValueError('Unresolved reference')
    try:
        ast.parse(code)
    except SyntaxError as exc:
        raise ValueError(f'Resolved Python syntax invalid: {exc.msg}') from exc
    return code
