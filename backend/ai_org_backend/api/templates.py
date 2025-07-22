from fastapi import APIRouter, HTTPException
from pathlib import Path

TEMPLATE_DIR = Path('prompts')

router = APIRouter(prefix='/api/templates', tags=['templates'])


def _safe(path: Path) -> Path:
    if not path.resolve().is_relative_to(TEMPLATE_DIR.resolve()):
        raise HTTPException(400, 'invalid path')
    return path


@router.get('/')
def list_files():
    return [p.name for p in TEMPLATE_DIR.glob('*.j2')]


@router.get('/{name}')
def get_file(name: str):
    path = _safe(TEMPLATE_DIR / name)
    if not path.exists():
        raise HTTPException(404)
    return {'content': path.read_text()}


@router.put('/{name}')
def save_file(name: str, body: dict):
    path = _safe(TEMPLATE_DIR / name)
    path.write_text(body.get('content', ''))
    return {'ok': True}
