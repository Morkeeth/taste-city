"""Build only browser assets into public; application sources stay server-side."""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent

def build():
    target = ROOT / 'public'
    target.mkdir(exist_ok=True)
    for name in ('village.html', 'match.html', 'pair.html', 'panel.html'):
        shutil.copy2(ROOT / name, target / name)
    # Recordings are served by the API, never copied as browser source.
    shutil.copytree(ROOT / 'vendor', target / 'vendor', dirs_exist_ok=True)

if __name__ == '__main__':
    build()
