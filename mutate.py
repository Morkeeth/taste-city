"""Mutation check: each mutation must turn the tests red. Runs on a temp copy. Output: mutate.out"""
import pathlib, shutil, subprocess, tempfile
HERE = pathlib.Path(__file__).resolve().parent
MUTS = [
    ("backtest.py", "statistics.median(w[t - 7:t + 1]) >= FLOOR]", "statistics.median(w[t - 7:t + 1]) >= 0]"),
    ("backtest.py", ">= JUMP * past[i]", "> JUMP * past[i] * 2"),
    ("backtest.py", "NEIGHBOUR_WEIGHT * (sum(nb)", "0 * (sum(nb)"),
    ("backtest.py", "return (dt.date.fromisoformat(sunday) - FIRST_MONDAY).days // 7", "return (dt.date.fromisoformat(sunday) - FIRST_MONDAY).days // 7 + 1"),
    ("backtest.py", "k1 = s[\"Q-P\"][\"ci\"][0] > 0", "k1 = s[\"Q-P\"][\"ci\"][1] > 0"),
    ("backtest.py", "K, FLOOR, JUMP, NEIGHBOUR_WEIGHT = 10, 700, 1.5, 1.0", "K, FLOOR, JUMP, NEIGHBOUR_WEIGHT = 10, 700, 1.4, 1.0"),
    ("radar.py", "archetype[\"tags\"] & set(e[\"tags\"])]", "set(e[\"tags\"])]"),
    ("radar.py", "pick[\"called_it\"] = ratio >= backtest.JUMP", "pick[\"called_it\"] = True"),
    ("radar.py", "out.append((backtest.momentum(w, t), i))", "out.append((backtest.momentum(w, min(t + 2, len(w) - 1)), i))"),
    ("app.py", "if week is not None and week not in self.weeks:\n            return None", "pass"),
    ("hipster.html", "el(\"span\", {}, \"Called it\")", "document.body.innerHTML = \"\""),
    (".gitignore", "\ncache/\n", "\ncachex/\n"),
]
lines = []
for f, old, new in [(".gitignore", "", "")] + MUTS:  # the first row is the control: no change, must stay green
    with tempfile.TemporaryDirectory() as d:
        dst = pathlib.Path(d) / "h"
        shutil.copytree(HERE, dst, ignore=shutil.ignore_patterns("cache", "__pycache__"))
        (pathlib.Path(d) / "demo").mkdir()
        shutil.copy(HERE.parent / "demo" / "live.py", pathlib.Path(d) / "demo" / "live.py")
        p = dst / f
        src = p.read_text()
        assert old in src, (f, old)
        if old:
            p.write_text(src.replace(old, new, 1))
        r = subprocess.run(["python3", "-m", "unittest", "test_hipster"], cwd=dst, capture_output=True, text=True)
        lines.append(f"{'RED ' if r.returncode else 'GREEN'} {f}: {old[:60]!r}" if old else
                     f"CONTROL {'GREEN' if r.returncode == 0 else 'RED, the harness is broken'}")
out = "\n".join(lines) + f"\n{sum(l.startswith('RED') for l in lines)} of {len(MUTS)} mutations red\n"
(HERE / "mutate.out").write_text(out); print(out)
