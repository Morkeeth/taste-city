"""One ask(model_key, prompt) for every answerer in the 29 Oct Qloo ladder.
Subscription: Opus 5.5, Fable 5.1, Sonnet 5.5 (claude -p), GPT-6.1-sol (codex exec), Composer 2.5 (cursor-agent, Oscar's
cursor-api-key-billing-29oct = YES). API key, Oscar's qloo-model-spend-29oct = YES ALL 4, cap 5.52 USD total:
Gemini 4 Argon (via OpenRouter: the GEMINI_API_KEY is free-tier and gets 429 for gemini-4-argon), Grok 4.7, Kimi K3.1 Pro, DeepSeek V4 Pro (OpenRouter). Every API call's cost goes to
spend.jsonl; ask() refuses once logged spend reaches the cap. Keys come from the environment and are never logged."""
import json, os, subprocess, tempfile, threading, time, urllib.request
from pathlib import Path
import ladder

OUT = Path(__file__).resolve().parent
SPEND, CAP_USD = OUT/'spend.jsonl', 5.52
_lock = threading.Lock()
SUB = {'opus': ('claude', 'claude-opus-5-5'), 'fable': ('claude', 'claude-fable-5-1'), 'sonnet': ('claude', 'claude-sonnet-5-5'),
       'gpt': ('codex', 'gpt-6.1-sol')}
API = {'gemini': ('openrouter', 'google/gemini-4-argon', 2.00, 10.00), 'grok': ('openrouter', 'x-ai/grok-4.7', 2.00, 6.00),
       'kimi': ('openrouter', 'moonshotai/kimi-k3.1-pro', 2.00, 10.00), 'deepseek': ('openrouter', 'deepseek/deepseek-v4-pro', 0.897, 1.795)}
ALL = list(SUB) + ['composer'] + list(API)


def spent():
    return sum(json.loads(l)['usd'] for l in SPEND.open()) if SPEND.exists() else 0.0


def _post(url, body, headers):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json', **headers})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(3 * 2 ** attempt); continue
            raise RuntimeError(f'HTTP {e.code}: {e.read().decode()[:200]}')
    raise RuntimeError('gave up after retries')


def ask(key, prompt, tag=''):
    if key in SUB:
        return ladder.run_cli(*SUB[key], prompt)
    if key == 'composer':
        with tempfile.TemporaryDirectory() as d:
            t0 = time.time()
            p = subprocess.run(['cursor-agent', '-p', '--trust', '--sandbox', 'enabled', '--model', 'composer-2.5', '--output-format', 'text', prompt],
                               cwd=d, capture_output=True, text=True, timeout=600)
            if p.returncode != 0 or not p.stdout.strip():
                raise RuntimeError(f'cursor-agent exit {p.returncode}: {p.stderr[:200]}')
            with _lock, (OUT/'cursor-calls.jsonl').open('a') as f:
                f.write(json.dumps({'at': ladder.now(), 'tag': tag, 'seconds': round(time.time()-t0, 1), 'cost': 'not reported by cli'})+'\n')
            return p.stdout.strip(), {'model': ['composer-2.5'], 'seconds': round(time.time()-t0, 1)}
    prov, model, pin, pout = API[key]
    with _lock:
        if spent() >= CAP_USD:
            raise RuntimeError(f'spend cap {CAP_USD} USD reached')
    t0 = time.time()
    if prov == 'google':
        j = _post(f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                  {'contents': [{'role': 'user', 'parts': [{'text': prompt}]}]}, {'x-goog-api-key': os.environ['GEMINI_API_KEY']})
        text = ''.join(p.get('text', '') for c in j.get('candidates', []) for p in c.get('content', {}).get('parts', []))
        u = j.get('usageMetadata', {}); tin = u.get('promptTokenCount', 0); tout = u.get('candidatesTokenCount', 0) + u.get('thoughtsTokenCount', 0)
        usd = tin/1e6*pin + tout/1e6*pout; src = 'tokens x list price'
    else:
        j = _post('https://openrouter.ai/api/v1/chat/completions', {'model': model, 'messages': [{'role': 'user', 'content': prompt}],
                  'usage': {'include': True}}, {'Authorization': 'Bearer ' + os.environ['OPENROUTER_API_KEY']})
        text = j['choices'][0]['message'].get('content') or ''
        u = j.get('usage', {}); tin, tout = u.get('prompt_tokens', 0), u.get('completion_tokens', 0)
        usd = u.get('cost'); src = 'openrouter usage.cost'
        if usd is None:
            usd = tin/1e6*pin + tout/1e6*pout; src = 'tokens x list price'
    with _lock, SPEND.open('a') as f:
        f.write(json.dumps({'at': ladder.now(), 'model': key, 'tag': tag, 'tokens_in': tin, 'tokens_out': tout, 'usd': round(usd, 6), 'source': src})+'\n')
    if not text.strip():
        raise RuntimeError(f'{key} returned empty text')
    return text.strip(), {'model': [model], 'seconds': round(time.time()-t0, 1), 'usd': round(usd, 6)}
