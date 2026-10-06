# Aria ATG Case

How good are ATG's customers at picking the winning horse?

Pick a game type. A small AI model running on your own computer (Harry AI, Qwen 3.5 2B) answers every leg of
the three latest finished games, and plain code checks every answer.

## Run

```
git clone https://github.com/ariakalantari/aria-atg-case.git
cd aria-atg-case
docker compose up
```

Open http://localhost:8000. The first start downloads the model (1.3 GB). No GPU or API key needed.

## How it works

1. `fetch.py` gets the three latest finished games from ATG's API.
2. `clean.py` drops scratched horses and sorts each leg by V-odds.
3. `ask.py` asks the model two small questions per leg: the three favourites (it sees only the odds), then where
   the favourite finished (it sees only the result).
4. `check.py` works out the same answers in code and compares.
5. `report.py` streams it all to the page.

**Favourite:** the lowest V-odds among the horses that started.

Harry AI (`agent.py`, `tools.py`) is the chat in the sidebar. It looks up the race data with tools and answers
in English or Swedish.

## Results

Over 153 legs and 10 game types, Qwen 3.5 2B got 150 legs fully right (98%) at 2.2 s per leg. The bigger 4B
model got 128 (84%) at 4.8 s. Run it again with `docker compose exec app python -m app.evaluate`.

## Tests

```
pip install -r requirements-dev.txt
python -m pytest
```

Built as a code case for ATG. Not an official ATG product.
