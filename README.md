# Aria ATG Case

How good are ATG's customers at picking the winning horse?

## The answer

On 6 October 2026, over the three latest finished games of all 10 game types (128 different races), the
customers' favourite (the horse with the lowest V-odds, the one most backed) won **36%** of the races. Its odds
gave it 38% on average, so the favourites won a little less often than their odds said. Half of them finished
2nd or better. In V85 alone the favourite won 10 of 24 legs (42%), more than the odds' 35%. Three games per
game type is a small sample, so these numbers move as new games finish.

## Run

```
git clone https://github.com/ariakalantari/aria-atg-case.git
cd aria-atg-case
docker compose up
```

Open http://localhost:8000 and pick a game type. An AI model on your own computer (Harry AI, Qwen 3.5 2B)
answers every leg of the three latest finished games, and plain code checks every answer. The first start
downloads the model once (1.3 GB); the page and the terminal show the progress. A new game type takes about
two minutes on a laptop CPU, after that the answers are saved. Needs Docker with Compose 2.24 or newer, no
GPU or API key.

From the command line: `docker compose exec app python -m app.report V86` prints the four answers as a table.
The API: `curl localhost:8000/api/report/V86` streams one JSON line per leg, then the summary.

## How it works

1. `fetch.py` gets the three latest finished games from ATG's API.
2. `clean.py` drops scratched horses and sorts each leg by V-odds.
3. `ask.py` asks the model two small questions per leg: the three favourites with their V-odds (it sees only
   the odds), then where the favourite finished and whether it won (it sees only the result).
4. `check.py` works out the same answers in code and checks each one.
5. `report.py` sums up and streams it all to the page. The local 2B model cannot count its own 24 answers
   (asked, it got the median right for 2 of 10 game types), so code counts them. In Claude mode the model
   sums up itself.

**Favourite:** the lowest V-odds among the horses that started. Ties go to the bigger bet share, then the
lower start number. A disqualified favourite counts as last.

Harry AI (`agent.py`, `tools.py`) is the chat in the sidebar. It looks up the race data with tools and
answers in English or Swedish.

## Results

The same 153 legs, answered fresh by both models on 6 October 2026:

| Model | Legs fully right | Median and wins | Time per leg | Cost per leg |
|-------|------------------|-----------------|--------------|--------------|
| Qwen 3.5 2B, local (default) | 147 (96%) | counted by code from its answers | 4.6 s | free |
| Claude Sonnet 4.6, Claude mode | 153 (100%) | by the model, 10 of 10 right | 3.2 s | about $0.003 |

Claude mode (the switch next to the flags) only runs on Aria's computer, so the API key is never shared.
With your own Foundry key, copy `.env.example` to `.env`. Measure it yourself with
`docker compose exec app python -m app.evaluate` (add `--claude` for Claude mode).

## Tests

On your own machine, with Python 3.10 or newer (the Docker image leaves the tests out):

```
pip install -r requirements-dev.txt
python -m pytest
```

Built as a code case for ATG. Not an official ATG product.
