# Working on Taste City

Read README.md first. Keep the personal-discovery and business-planning paths clear while preserving the 3D city.

## Code map

- `match_app.py`: local server, port 8811 by default; optional port argument.
- `village.html`: main browser UI; bundled Three.js is in `vendor/`.
- `api/`: Vercel Python entry points reused by the local server.
- `taste_city.py`, `local_places.py`, `qloo_client.py`: taste discovery, address/radius handling and provider access.
- `sample_demo.py`: explicitly fictional no-key results.
- `benchmark/qloo-vs-frontier-2026-10/`: frozen experiment, redacted source data, harness and limits.
- `docs/images/`: real hosted-product screenshots, dated and explained in README.md.
- `docs/figures/plot_location_benchmark.py`: reproduces the README chart from published counts; optional matplotlib dependency.

## Safe first checks

Use Python 3.12 and the README environment setup. `python3 -m unittest` and `python3 build_static.py` require no provider access. The optional private-recording test may skip. Do not create a private recording just to turn the skip green.

For a UI check, run `python3 match_app.py <unused-port>` and open `/?demo=1&setup=1`. Sample mode is fictional and makes no Qloo or model request. Do not replace a running service to obtain a port. Stop only the process you started.

## Evidence and data boundaries

- Keep live, exact-input recorded and fictional sample results visibly distinct.
- Qloo affinity is a cultural relationship, not demand, preference or a sales forecast.
- Nearby distances use the matched centre and straight-line geometry. Preserve the radius check and explicit errors; never silently widen the search.
- Audience tastes in business mode are a planner hypothesis, not a customer survey.
- The location benchmark verifies proximity against incomplete OpenStreetMap coverage; it does not score audience fit. Read counts and denominators before repeating a percentage.
- Keep credentials, raw Qloo responses, provider caches, private transcripts and machine-specific paths out of code, fixtures, logs and git. Use synthetic fixtures. Existing public product screenshots document the interface, not a reusable provider dataset.
- Provider calls consume quota or money. Get an explicit run budget before new live experiments; a no-key sample is enough for routine UI checks.

## Shipping

Use an isolated branch/worktree. Read the current diff before editing. For documentation-only changes, check links, figure source counts and rendered images; do not invent product outcomes or claim a suite ran when it did not.

`deploy.sh` targets the existing Vercel owner/project and runs checks; production credentials belong in the hosting secret store. Deployment, publication and hackathon submission are separate actions. Obtain the corresponding authorization and verify the live object afterward.
