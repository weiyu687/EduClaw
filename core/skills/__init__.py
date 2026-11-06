from pathlib import Path
from .registry import SkillRegistry

BUILTIN_SKILLS=Path(__file__).resolve().parents[2]/'skills'

def registry_for(directory):
    return SkillRegistry(BUILTIN_SKILLS,Path(directory)/'installed-skills')
