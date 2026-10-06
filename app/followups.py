"""Follow-up ideas after each Harry answer: two or three short questions to ask next.

Code does most of the work, the model only chooses:
1. Preset ideas from what Harry just looked up (the tools it ran, with their tracks, legs and
   horses), like the suggestions in an empty chat. The tools can always answer them.
2. When Harry looked up race data, the model picks the two ideas that fit the conversation best
   and may write one short question of its own (forced into a small JSON schema).
3. Code checks the result and falls back to the preset ideas if anything is off.
"""
import httpx

from . import ask, fetch, tools
from .clean import Game
from .words import answer_language, say

LEGS = {"V85": 8, "V86": 8, "GS75": 7, "V64": 6, "V65": 6, "V5": 5, "V4": 4, "V3": 3, "dd": 2, "ld": 2}
NO_POOL = {"dd", "ld"}  # no bet share, so nothing to compare with the odds
MAX_LENGTH = 48         # longer chips do not fit the panel on a phone


async def suggest(client: httpx.AsyncClient, messages: list[dict], answer: str, turn: list[tuple[dict, dict | None]],
                  page_type: str, games: list[Game], lang: str) -> list[str]:
    """Up to three follow-up questions. turn holds (call, view) for each tool Harry ran this time."""
    asked = {tools.plain(m["content"]) for m in messages if m["role"] == "user"}
    ideas = [idea for idea in candidates(turn, page_type, games, lang) if tools.plain(idea) not in asked][:6]
    if not turn or len(ideas) < 3:  # small talk, words and rules, or a polite no: preset ideas, no model call
        return ideas[:3]
    try:
        reply = await ask.ask(client, *prompt(messages[-1]["content"], answer, turn, ideas, lang))
        return choose(reply, ideas, asked, lang, answer)
    except Exception:  # follow-ups are an extra: any failure falls back to the preset ideas
        return ideas[:3]


def candidates(turn: list[tuple[dict, dict | None]], page_type: str, games: list[Game], lang: str) -> list[str]:
    """Preset ideas, best first: from each tool Harry ran, then general ones for the page."""
    ideas = []
    for call, view in turn:
        ideas += ideas_after(call["name"], call["arguments"], view, page_type, games, lang)
    ideas += [
        say(lang, "Summarise {game_type}", game_type=page_type),
        say(lang, "Biggest upsets in {game_type}", game_type=page_type),
        say(lang, "Compare all game types"),
        say(lang, "Is the favourite a good bet?"),
    ]
    if games:
        ideas.append(say(lang, "Show leg {leg} at {track}", leg=1, track=games[0].track))
    ideas.append(say(lang, "What does V-odds mean?"))
    return list(dict.fromkeys(ideas))  # no duplicates, order kept


def ideas_after(name: str, args: dict, view: dict | None, page_type: str, games: list[Game], lang: str) -> list[str]:
    """What people likely want after one tool: the next leg, the whole game, the upsets, and so on."""
    game_type = args.get("game_type") if args.get("game_type") in fetch.GAME_TYPES else page_type
    rows = (view or {}).get("rows") or []

    def idea(text: str, **values) -> str:
        return say(lang, text, **{"game_type": game_type, **values})

    def show_leg(cell: dict) -> str:  # cell: {"leg": 7, "track": "Boden"}, track may be missing
        if cell.get("track"):
            return idea("Show leg {leg} at {track}", **cell)
        return idea("Show leg {leg} in {game_type}", leg=cell["leg"])

    upsets, summary = idea("Biggest upsets in {game_type}"), idea("Summarise {game_type}")
    good_bet, compare = idea("Is the favourite a good bet?"), idea("Compare all game types")
    bets = [] if game_type in NO_POOL else [idea("Bets against odds in {game_type}")]
    if name == "favourite_stats":
        return [upsets, compare, good_bet, *bets]
    if not rows:  # the tool found nothing (a leg that does not exist, an unknown track)
        return []
    if name == "compare_game_types":
        best, worst = rows[0]["game"], rows[-1]["game"]
        return [idea("Summarise {game_type}", game_type=best), idea("Biggest upsets in {game_type}", game_type=worst), good_bet]
    if name == "leg_details":
        track = track_for(args, game_type, page_type, games)
        number = args["leg"]
        other = number + 1 if number < LEGS.get(game_type, 0) else number - 1  # the next leg, or the one before the last
        whole = [idea("Show all legs at {track}", track=track)] if track else []
        return [show_leg({"leg": other, "track": track}), *whole, upsets]
    if name == "game_overview":
        track = rows[0]["leg"]["track"]
        surprises = sorted((row for row in rows if row["finish"] != "1" and row["winner"]), key=lambda row: -row["winner_odds"])
        others = [game.track for game in games if game.track != track] if game_type == page_type else []
        return [*(show_leg(row["leg"]) for row in surprises[:1]),
                *(idea("Show {game_type} at {track}", track=other) for other in others[:1]), upsets, summary]
    if name == "upsets":
        return [*(show_leg(row["leg"]) for row in rows[:2]), good_bet, *bets]
    if name == "bets_vs_odds":
        return [show_leg(rows[0]["leg"]), upsets, summary]
    if name == "find_horse":
        return [show_leg(rows[0]["leg"]), idea("Show all legs at {track}", track=rows[0]["leg"]["track"]), upsets]
    return []


def track_for(args: dict, game_type: str, page_type: str, games: list[Game]) -> str | None:
    """The track a leg was looked up at, spelled the way ATG spells it when we have the games."""
    track = str(args.get("track") or "")
    if game_type != page_type or not games:
        return track or None
    game = tools.pick_game(games, track)
    return game.track if game else None


def prompt(question: str, answer: str, turn: list[tuple[dict, dict | None]], ideas: list[str], lang: str) -> tuple[str, dict]:
    facts = "\n".join(f"- {fact}" for call, _ in turn for fact in call["facts"][:4])
    options = "\n".join(f"- {idea}" for idea in ideas)
    language = "Swedish, with ATG's words (avdelning, omgång, spelform, favorit, skräll)" if lang == "sv" else "English"
    text = (
        f"Someone asked Harry, the assistant on a page about ATG horse racing results: {question}\n"
        f"Harry looked up:\n{facts}\nHarry answered: {answer[:400]}\n\n"
        f"Ideas for what to ask next:\n{options}\n\n"
        "Pick the two ideas they would most likely ask next. Then write one new question in "
        f"{language}, at most 8 words, about something Harry's answer did not cover yet. It must be answerable "
        "from the latest three games (their favourites, odds, winners, upsets, legs or horses), so nothing about "
        "years, drivers, trainers or coming races. Leave it empty if no good question fits."
    )
    schema = {
        "type": "object",
        "properties": {
            "picks": {"type": "array", "items": {"type": "string", "enum": ideas}, "minItems": 2, "maxItems": 2},
            "question": {"type": "string", "maxLength": MAX_LENGTH},
        },
        "required": ["picks", "question"],
    }
    return text, schema


def choose(reply: dict, ideas: list[str], asked: set[str], lang: str, answer: str = "") -> list[str]:
    """The model's two picks, then its own question if it passes the checks, then preset ideas up to three."""
    picks = [pick for pick in reply.get("picks", []) if pick in ideas][:2]
    own = " ".join(str(reply.get("question") or "").split()).strip("\"' ")
    # A small model likes to ask what the answer just said ("Who won leg 4 at Åby?" right after
    # saying who won it), so its question must name something new: a leg, a horse or a track.
    # The schema cuts a long question off mid-word, and a cut question has no question mark.
    covered = {tools.plain(word) for word in f"{answer} {' '.join(picks)}".split()}
    if not (8 <= len(own) <= MAX_LENGTH and own.endswith("?")) or answer_language(own, lang) != lang or names(own) <= covered:
        own = ""
    chosen = []
    for question in [*picks, own, *ideas]:
        if question and tools.plain(question) not in asked | {tools.plain(c) for c in chosen}:
            chosen.append(question)
    return chosen[:3]


def names(question: str) -> set[str]:
    """What a question is about: its numbers and capitalised words (after the first word)."""
    words = question.replace("?", " ").split()
    return {tools.plain(word) for n, word in enumerate(words) if word[0].isdigit() or (n and word[0].isupper())}
