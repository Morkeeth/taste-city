# Taste City

Explore culture through taste, then bring the results into a playful 3D city.

[Open Taste City](https://taste-city.vercel.app/) · [Try the fictional no-key sample](https://taste-city.vercel.app/?demo=1&setup=1)

## Judge path

1. Open the fictional sample. Choose **For a coffee shop: test** to compare ideas, or **For me: discover** to explore tastes. Sample results are invented; they do not prove a live Qloo request or customer demand.
2. For a live run, return to the app without `demo=1`. Qloo access must be configured on the server. A live request uses Qloo quota; the Taste Agent does not need an LLM key. Inspect the source-call/entity trail and the conditions that should drop an idea.
3. To reproduce without API access, clone the public source and follow the sample setup and tests below. Tests use synthetic providers, so passing them establishes implementation behavior, not Qloo superiority or real audience preference.
4. Business spending and feasibility inputs are planner assumptions. Cultural affinity, demand and sales are different claims; do not read a fit score as a demand forecast.

- **For a coffee shop: test** is the main route. A coffee-shop owner sets three tastes they think their customers share and compares two ideas, such as a pop-up or a late event, against a taste graph. Cultural fit and the planner's spending assumptions stay separate. Save and reopen a local action brief with a budget and feasibility checks. A festival planner can use the same flow.
- **Live Taste Agent** follows one cited cultural lead into another Qloo domain, checks that result and proposes a small test. The card shows the returned entity ID, the follow-up query seeded with it, the result and the conditions that should drop the idea. It uses up to 11 Qloo HTTP reads including retries and needs no model key.
- **For me: discover** takes three favourites and a food city, then finds music, film, food, books and places through Qloo. Each result carries its source call.
- **City and gift game** keeps the Sims-style city, residents, outlets, subway, festival and day/night cycle available from the header.

Qloo affinity describes cultural relationships. It does not predict demand, sales, attendance, conversion or partner availability. The business audience is a planner hypothesis.

## Run locally

Use Python 3.12 and install the dependencies:

```sh
git clone https://github.com/Morkeeth/taste-city.git
cd taste-city
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python3 match_app.py
```

Open http://127.0.0.1:8811/?demo=1&setup=1 for the two starting paths with fictional sample data. The sample makes no Qloo or model call. Its default discovery tastes and city are fixed; arbitrary tastes need live Qloo.

For live discovery, business comparisons, the live agent and city population, set `QLOO_API_KEY` in the server process, then open http://127.0.0.1:8811/. Keys stay on the server. Supply them through your environment or hosting secret store, never client code or source control.

The optional Matchmaker needs `ANTHROPIC_API_KEY`. Persistent legacy pair links need `KV_REST_API_URL` and `KV_REST_API_TOKEN`; without Redis, serverless pair links are temporary. The two main starting paths and the live Taste Agent do not require these optional services.

A public brand website can provide visible source cues. Confirm its resolved entity before treating its graph as the brand source; customer tastes remain unmeasured. Confirm or change audience tastes before comparing ideas.

## Verify

```sh
python3 -m unittest
python3 build_static.py
```

Tests use local synthetic providers and make no external Qloo or model call. A test for an optional private recording skips when that recording is absent. Public source contains no provider recordings or runtime cache. Browser capture helpers in `tests/` are optional and require `requirements-dev.txt` plus Playwright; do not run their live modes unless you intend to use API quota.

`build_static.py` copies only browser HTML and the bundled Three.js files into `public/`. `api/` contains the matching Vercel Python handlers. The local server uses those same handlers.

## Host

`vercel.json` configures Python functions, static build output and routes. Set `QLOO_API_KEY` in the production server environment. `deploy.sh` is guarded for the existing `taste-city` project and owner; it checks the link and production key name, builds static assets and runs the suite before deployment. It does not configure credentials.

Qloo data is fetched live into ignored caches; repeated exact business choices can use a visibly labelled recording. Clean source uses fictional sample results only in sample mode. Missing keys and unavailable results remain explicit.

## License and data

MIT; see `LICENSE`. Bundled Three.js retains its license in `vendor/THREE-LICENSE`. Qloo results are service data and are not included in this source release. The city can pair returned public Wikidata references with English Wikipedia pageviews; pageviews measure attention rather than taste.

### Nearby discovery

The **For me** flow accepts an address or postcode with its city/country and a
500 m, 1 km or 1.5 km radius. OpenStreetMap Nominatim resolves that input to a
matched centre; the UI shows the matched address so it can be checked. Qloo
receives `filter.location=POINT(longitude latitude)` and
`filter.location.radius` for restaurant recommendations, seeded by the same
three taste entities. Less mainstream discovery also sets
`filter.popularity.max=0.5`; users can turn that option off. The server rejects
places with missing or out-of-radius coordinates. Results show Qloo entity IDs,
source calls and straight-line distance, not a walking-distance claim.

No extra API key is needed for address lookup. If lookup or Qloo is unavailable,
the app reports that failure or uses an explicitly labelled recording for the
exact same input, radius and discovery setting. It never silently broadens a
local search. The fictional sample and business scenario flows keep their
existing setup and provenance labels.
