#!/bin/sh
# Oscar-only outward action. Recording, environment setup and deployment are his clicks.
set -eu
cd "$(dirname "$0")"
python3 - <<'PY'
import json
from pathlib import Path
path = Path('.vercel/project.json')
if not path.exists():
    raise SystemExit('Stop: link this folder to the existing taste-city project before deployment.')
link = json.loads(path.read_text())
expected = {'projectName': 'taste-city',
            'projectId': 'prj_9TBxqKheaq77YSKxlI9ssKpFWwUq',
            'orgId': 'team_pyn313moYAPrdTjKeJJeCkoL'}
if any(link.get(key) != value for key, value in expected.items()):
    raise SystemExit('Stop: linked Vercel project or owner differs from the verified taste-city target.')
PY
key_list=$(vercel env ls production --no-color)
printf '%s\n' "$key_list" | python3 -c 'import re,sys; text=sys.stdin.read(); sys.exit(0 if re.search(r"(^|\s)QLOO_API_KEY(\s|$)", text) else "Stop: QLOO_API_KEY is missing from the production environment.")'
python3 build_static.py
python3 -m unittest
exec vercel deploy --prod --yes
