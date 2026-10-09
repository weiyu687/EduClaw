"""Small, deterministic Skill registry. Skill instructions are untrusted guidance."""
from pathlib import Path
import re

class SkillRegistry:
    def __init__(self, root='skills'):
        self.root = Path(root)

    def list(self):
        out = []
        for f in sorted(self.root.glob('*/SKILL.md')):
            raw = f.read_text(encoding='utf-8')
            header = re.match(r'\A---\s*\n(.*?)\n---\s*\n', raw, re.S)
            metadata = {}
            if header:
                for line in header.group(1).splitlines():
                    if ':' in line:
                        k, v = line.split(':', 1)
                        metadata[k.strip()] = v.strip().strip('"\'')
            out.append({'id': f.parent.name, 'name': metadata.get('name', f.parent.name),
                        'description': metadata.get('description', ''), 'version': metadata.get('version', '')})
        return out

    def load(self, skill_id):
        if not isinstance(skill_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', skill_id):
            raise ValueError('Invalid skill identifier')
        file = self.root / skill_id / 'SKILL.md'
        if not file.is_file():
            raise LookupError('Skill not found')
        raw = file.read_text(encoding='utf-8')
        return re.sub(r'\A---\s*\n.*?\n---\s*\n', '', raw, count=1, flags=re.S).strip()
