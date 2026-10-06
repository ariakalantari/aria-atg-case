"""Swedish for the few texts the server shows on the page (Harry's tool labels and tables).
The words follow ATG's own (avdelning, omgång, spelform, spelprocent, skräll), checked against atg.se.

The English text is the key, so the code reads in plain English:
    say("sv", "Leg {leg}, {track}", leg=7, track="Boden")  ->  "Avdelning 7, Boden"
Facts for the model stay in English. Harry answers in the language of the question (answer_language).
"""
import re
from datetime import datetime

SWEDISH = {
    # what Harry did (tool labels)
    "Compared every game type": "Jämförde alla spelformer",
    "Looked for {game_type} games": "Letade efter {game_type}-omgångar",
    "Counted the favourites in {game_type}": "Räknade favoriterna i {game_type}",
    "Opened {game_type} at {track}": "Öppnade {game_type} på {track}",
    "Looked up leg {leg} at {track}": "Slog upp avdelning {leg} på {track}",
    "Looked for upsets in {game_type}": "Letade efter skrällar i {game_type}",
    "Compared bets with odds in {game_type}": "Jämförde spelprocent med odds i {game_type}",
    "Searched for {horse}": "Sökte efter {horse}",
    "Tried an unknown tool": "Försökte med ett okänt verktyg",
    "I could not finish that one. Try asking about one game or one leg.":
        "Det där hann jag inte klart med. Fråga gärna om en omgång eller en avdelning.",
    # table titles
    "Favourites in {game_type}": "Favoriter i {game_type}",
    "Favourites in every game type": "Favoriter i alla spelformer",
    "Leg {leg}, {track}": "Avdelning {leg}, {track}",
    "Biggest upsets in {game_type}": "Största skrällarna i {game_type}",
    "Bets against odds in {game_type}": "Spelprocent mot odds i {game_type}",
    "{horse} in {game_type}": "{horse} i {game_type}",
    # tiles, columns and cells
    "Favourite won": "Favoriten vann",
    "Median finish": "Medianplacering",
    "Odds expected": "Oddsen trodde",
    "{a} of {b}": "{a} av {b}",
    "Game": "Omgång",
    "Game type": "Spelform",
    "Legs": "Avd.",
    "Leg": "Avd",
    "Fav. won": "Fav. vann",
    "Odds said": "Oddsen sa",
    "Median": "Median",
    "Favourite": "Favorit",
    "Winner": "Vinnare",
    "Horse": "Häst",
    "Finish": "Plac.",
    "Fav. finish": "Fav. plac.",
    "Odds favourite": "Oddsfavorit",
    "Most bet": "Mest spelad",
    "Odds rank": "Nr i oddsen",
    "No. {n} in the odds": "Nr {n} i oddsen",
    " or worse": " eller sämre",
    # follow-up ideas under an answer (short, like ATG's own suggestion chips)
    "Show leg {leg} at {track}": "Visa avdelning {leg} på {track}",
    "Show leg {leg} in {game_type}": "Visa avdelning {leg} i {game_type}",
    "Show all legs at {track}": "Visa alla avdelningar på {track}",
    "Show {game_type} at {track}": "Visa {game_type} på {track}",
    "Summarise {game_type}": "Sammanfatta {game_type}",
    "Compare all game types": "Jämför alla spelformer",
    "Is the favourite a good bet?": "Lönar det sig att spela på favoriten?",
    "What does V-odds mean?": "Vad betyder V-odds?",
}

DAYS = ["måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"]
MONTHS = ["januari", "februari", "mars", "april", "maj", "juni", "juli",
          "augusti", "september", "oktober", "november", "december"]


def say(lang: str, text: str, **values) -> str:
    template = SWEDISH.get(text, text) if lang == "sv" else text
    return template.format(**values)


def day(start: str, lang: str = "en") -> str:
    """ "2026-10-03T15:08:18" -> "Saturday 3 October" or "lördag 3 oktober" """
    date = datetime.fromisoformat(start)
    if lang == "sv":
        return f"{DAYS[date.weekday()]} {date.day} {MONTHS[date.month - 1]}"
    return f"{date:%A} {date.day} {date:%B}"


def ordinal(n: float, lang: str = "en") -> str:
    """2 -> "2nd" or "2:a". Halves (a median of 1.5) stay as numbers."""
    if n != int(n):
        return f"{n:g}".replace(".", ",") if lang == "sv" else f"{n:g}"
    n = int(n)
    if lang == "sv":
        return f"{n}:{'a' if n % 10 in (1, 2) and n % 100 not in (11, 12) else 'e'}"
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


# Which language to answer in (used for Harry's answers and its follow-up ideas)
SWEDISH_HINTS = {"och", "är", "vad", "vilken", "vilka", "hur", "jag", "på", "som", "inte", "med", "för", "kan", "visa",
                 "var", "den", "det", "ett", "om", "har", "spela", "avdelning", "omgång", "favoriten", "hej", "tack",
                 "sammanfatta", "spelprocent", "mot", "alla"}
ENGLISH_HINTS = {"the", "what", "which", "how", "is", "was", "show", "me", "did", "does", "of", "and", "a", "who",
                 "why", "can", "you", "hi", "hello", "thanks", "biggest", "leg", "game", "favourite", "favorite",
                 "summarise", "summarize", "bets", "against", "compare"}


def answer_language(question: str, page_lang: str) -> str:
    """Answer in the language the question is written in. When that is unclear ("V85?"), use the
    page's language. Plain code decides this, because a small model often gets it wrong."""
    text = question.lower()
    words = re.findall(r"[a-zåäö]+", text)
    swedish = sum(word in SWEDISH_HINTS for word in words) + (2 if re.search("[åäö]", text) else 0)
    english = sum(word in ENGLISH_HINTS for word in words)
    if swedish != english:
        return "sv" if swedish > english else "en"
    return page_lang
