# Does Qloo make frontier models better? A benchmark, October 2026

Short answer: **not at writing taste advice, yes at finding real places near an address.**

We first asked whether Qloo taste data makes a frontier model give better advice. Against a fair control it did not. Then we asked a question with a checkable answer: name real places within 500 m of an address in a smaller city. On that task, one change, Qloo's location filter, lifted every model we tested to the same high level.

Everything here was run on 29 October 2026. The code in `harness/` is the code that produced these numbers, with only private paths and Qloo IDs removed.

## Result 1: real places near an address (the main result)

**Task.** "Which 5 real places within 500 metres of [address] would this audience go to: independent record shops, listening bars, independent cinemas, small music venues or cafes?" There are 15 questions in total. The first 10 use 10 addresses (Leeds, Lyon, Ghent, Porto, Paris 19e, Bristol, Manchester, Marseille, Antwerp, Valencia) with audience A, fans of Björk, Radiohead and Little Simz. The other 5 reuse 5 of those addresses with audience B, fans of Ezra Collective, Nubya Garcia and Moses Boyd.

**Two steps, one change.**
- Step 0, the control: the audience description and the question.
- Step 1: the same, plus the places Qloo returns within 500 m of the address for that audience (`filter.location`, radius 500 m, up to 25 places), fetched once and frozen before any answer.

**Scoring needs no judge.** A named place counts when OpenStreetMap puts it within 500 m of the address. The scorer first runs a Nominatim bounded search; when that fails, it fuzzy-matches the name against every named OpenStreetMap feature within 1.5 km (Overpass).

| Model | Step 0 (no Qloo) | Step 1 (Qloo location filter) | Questions better / same / worse | Sign test p |
|---|---|---|---|---|
| Cursor Composer 2.5 | 39% (29/75) | 83% (62/75) | 13 / 2 / 0 | 0.0002 |
| Claude Sonnet 5.5 | 54% (44/82) | 85% (64/75) | 12 / 3 / 0 | 0.0005 |
| Kimi K3.1 Pro | 49% (37/75) | 83% (62/75) | 13 / 1 / 1 | 0.0018 |
| DeepSeek V4 Pro | 48% (36/75) | 84% (63/75) | 12 / 2 / 1 | 0.0034 |
| Claude Fable 5.1 | 68% (51/75) | 88% (66/75) | 9 / 4 / 2 | 0.065 |
| Gemini 4 Argon | 61% (46/75) | 85% (64/75) | 9 / 2 / 4 | 0.27 |
| GPT-6.1 | 73% (55/75) | 85% (64/75) | 7 / 4 / 4 | 0.55 |
| Claude Opus 5.5 | 77% (58/75) | 87% (65/75) | 7 / 6 / 2 | 0.18 |
| Grok 4.7 | 83% (50/60) | 87% (65/75) | 7 / 6 / 2 | 0.18 |

Percentages are the share of named places verified within 500 m. Denominators differ when a model named more or fewer than 5 places, or when an answer was not a parseable list. The p values come from a two-sided sign test over the 15 questions. Source: `data/hard-g1/result-combined-15-questions.json`.

**What it shows:**
- With Qloo's location filter, all 9 models end at 83 to 88%.
- The gain is clear for 4 models (Composer, Sonnet, Kimi, DeepSeek), whose own local knowledge is weakest.
- The strongest models were already at 68 to 83%, so their gain is smaller and not significant with 15 questions.
- Qloo works as a floor: every model ends up at the same level.
- Audience B replicates audience A (`data/hard-g1-audience-b/result-audience-b.json`).

**Dead end, reported:** keeping only the model's own picks that Qloo also lists. Qloo's list matches only 9 to 21 of each model's 50 picks, so this filter throws away as many real nearby places as it keeps (`data/hard-g1/hybrid-filter-dead-end.json`).

## Result 2: better advice prose (null)

Before Result 1 we tested what most demos claim: Qloo context makes the AI's advice better. We used 10 frozen business questions for a London coffee shop, with three arms: no context, the audience description only, and the audience plus 17 recorded Qloo entities. Answers came from Claude Opus 5.5 and GPT-6.1 and were graded blind by the other model, 3 passes each.

- First run: Qloo scored +9.0% and +3.0%. But the Qloo prompt alone carried a sentence ("affinity is a taste signal, not demand"), and half the Qloo answers echoed it as a test proposal.
- Rerun, with that sentence in every arm: **-3.5% (Opus) and -0.4% (GPT).** No gain.

The recorded Qloo entities for that audience were famous (Qloo popularity 0.98 to 0.999), which a frontier model already knows. Published research predicts this: models are competitive on popular entities and weak on rare ones (Mallen et al., ACL 2023; Kandpal et al., ICML 2023). That question was wrong for Qloo. Result 1 is the question it is right for.

## Result 3: what frontier models know of Qloo's long tail

We gave each model 20 lesser-known London places and 20 lesser-known artists from Qloo, plus 5 invented places and 5 invented artists. Each model had to give the place's postcode district (or UNKNOWN) and say whether it knew each artist (or UNKNOWN).

- **No model invented any decoy.** Given the option to say UNKNOWN, all 9 refused all 10 fakes.
- Correct postcode district for real places: 8 to 16 of 20. Sonnet gave 6 wrong districts with confidence.
- Models said they knew 7 to 18 of the 20 artists, but the genre they gave matched Qloo's tags for only 1 to 5.

So frontier models do not make places up here; they lack coverage. That is the gap Qloo filled in Result 1. Source: `data/knowledge-probe/`.

## Result 4: lesser-known artists, films and books

Same two steps on lesser-known artists, films and books, with Qloo's popularity filter as the one change, checked against MusicBrainz, Wikidata, Open Library and Wikipedia views. Still being scored on 29 October; it will be added in a follow-up commit.

## Limits

- **n:** 15 questions per model for Result 1, two audiences, one task family. Read the p values for what they are.
- **Fit is not scored.** We measured whether a place exists near the address, not whether it suits the audience. Qloo's own list included noise, such as a car-sharing bay in Ghent.
- **OpenStreetMap is the ground truth, and it is incomplete.** A real place missing from OpenStreetMap counts against the model that named it. Step 0 names not found in OpenStreetMap are unverified, not proven invented; several are real (for example La Machine à Coudre in Marseille).
- **Qloo is not ground truth either.** Its popularity score is not fame (Borough Market 0.384), and some descriptions are wrong.
- **Recording note for Result 2:** two Qloo recordings from 23 and 24 October share one cache file name and differ in one entity (Tate Modern vs Caffè Estorick). The 29 October Result 2 runs used entities that are identical in both. One earlier exploratory bench used the 23 October copy.
- **Edited data:** one model answer contained a visitportugal.com link with a GUID; the GUID was replaced with `[guid-removed]` so the repo's no-Qloo-ID test passes.
- **Withheld data:** Qloo's responses (names, addresses, tags) are not in git, by this repo's policy. Each frozen input file is published with that content withheld, and with the sha256 of the original.

## Rerun it

You need a Qloo API key (`QLOO_API_KEY`), the `claude` and `codex` CLIs for the subscription models, `cursor-agent` for Composer, and `OPENROUTER_API_KEY` for Gemini, Grok, Kimi and DeepSeek. All lookups to OpenStreetMap, Wikidata, MusicBrainz and Open Library are free and paced to their usage policies, at most one request per second.

```
cd harness
python3 hard.py context     # 10 Qloo calls: places within 500 m of each address
python3 hard.py freeze      # hashes the questions, prompts and Qloo context before any answer
python3 hard.py answer 0_control
python3 hard.py answer 1_qloo_location
python3 hard.py score 0_control && python3 hard.py score 1_qloo_location
python3 overpass_fetch.py   # named OpenStreetMap features within 1.5 km of each point
python3 resolve.py          # Overpass second pass
python3 hardb.py context && python3 hardb.py freeze && python3 hardb.py answer 0_control && python3 hardb.py answer 1_qloo_location && python3 hardb.py score
```

Fresh Qloo results and newer models will give different numbers. The protocol is what is frozen.

**Cost of the 29 October run:** 35 Qloo calls on the hackathon key; $2.25 of API spend for Gemini, Grok, Kimi and DeepSeek through OpenRouter (`data/api-spend.jsonl`); Claude, GPT and Composer ran on subscriptions.

OpenStreetMap data © OpenStreetMap contributors, ODbL.
