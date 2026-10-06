// English and Swedish for everything on the page. The English text is the key, so the code reads
// in plain English:  t("Favourite won {w} of {n}", { w: 2, n: 8 })  ->  "Favoriten vann 2 av 8"
// Static text is marked with data-i18n in index.html. The choice is remembered in this browser.
// The Swedish follows ATG's own words where they have one (avdelning, omgång, spelform, spelprocent,
// skräll, strukna, "Sammanfatta ...", "Skriv till ... här", "Tolkar fråga"), checked against atg.se.

const SWEDISH = {
  // top bar and intro
  "Language": "Språk",
  "How good are our customers at picking the winner?": "Hur bra är våra kunder på att välja vinnaren?",
  "Pick a game type. Harry AI, a small AI model on this computer, answers every leg of its three latest games, and plain code checks every answer.":
    "Välj en spelform. Harry AI, en liten AI-modell på den här datorn, svarar på varje avdelning i de tre senaste omgångarna, och vanlig kod kontrollerar varje svar.",
  "The 3 latest games": "De 3 senaste omgångarna",
  "Every answer checked": "Varje svar kontrollerat",
  "Runs on this computer": "Körs på den här datorn",
  "Game type": "Spelform",
  "Games": "Omgångar",
  "Legs": "Avdelningar",
  "Answered by": "Svar av",

  // progress and errors
  "Fetching the latest games from ATG": "Hämtar de senaste omgångarna från ATG",
  "Harry is answering leg {n} of {total}": "Harry svarar på avdelning {n} av {total}",
  "Counting": "Räknar",
  "Lost contact with the app. Check that it is still running.": "Tappade kontakten med appen. Kontrollera att den fortfarande körs.",
  "ATG has no finished {type} games right now.": "ATG har inga avgjorda {type}-omgångar just nu.",
  "The local model is not ready yet. It may still be downloading or loading.":
    "Den lokala modellen är inte redo än. Den laddas kanske fortfarande ner eller startar.",
  "Could not get data from ATG right now. Please try again in a moment.": "Kunde inte hämta data från ATG just nu. Försök igen om en liten stund.",
  "Something went wrong. Please try again.": "Något gick fel. Försök igen.",

  // Harry's answers to the four questions
  "Harry's answers to the four questions": "Harrys svar på de fyra frågorna",
  "The three favourites in each leg, with name and V-odds": "De tre favoriterna i varje avdelning, med namn och V-odds",
  "Whether the favourite won": "Om favoriten vann",
  "The favourite's median finishing position": "Favoritens medianplacering",
  "How often the favourite wins": "Hur ofta favoriten vinner",
  "All {n} legs": "Alla {n} avdelningar",
  "See every leg below": "Se alla avdelningar nedan",
  "Won {w} of {n}": "Vann {w} av {n}",
  "Harry also answered the median and win rate": "Harry svarade också på medianen och vinstandelen",
  "Median and win rate counted by code from Harry's answers": "Median och vinstandel räknade av koden utifrån Harrys svar",
  "The answer: the customers' favourite won {w} of {n} legs ({pct}). The odds gave it {odds}, so it won more often than the odds expected.":
    "Svaret: kundernas favorit vann {w} av {n} avdelningar ({pct}). Oddsen gav den {odds}, så den vann oftare än oddsen väntade.",
  "The answer: the customers' favourite won {w} of {n} legs ({pct}). The odds gave it {odds}, so it won less often than the odds expected.":
    "Svaret: kundernas favorit vann {w} av {n} avdelningar ({pct}). Oddsen gav den {odds}, så den vann mer sällan än oddsen väntade.",
  "The answer: the customers' favourite won {w} of {n} legs ({pct}). The odds gave it {odds}, and it won just as often.":
    "Svaret: kundernas favorit vann {w} av {n} avdelningar ({pct}). Oddsen gav den {odds}, och den vann precis så ofta.",
  "Half of the favourites finished {x} or better": "Hälften av favoriterna kom {x} eller bättre",
  "{a} of {b} ({pct})": "{a} av {b} ({pct})",
  "The odds gave it a {x} chance": "Oddsen gav {x} vinstchans",
  "{k} of {n} right": "{k} av {n} rätt",
  "{right} of {checked} answers right, checked by code": "{right} av {checked} svar rätt, kontrollerat av koden",
  "Code agrees": "Stämmer med koden",
  "Wrong, code counted {n}": "Fel, koden räknade {n}",
  "Wrong, code got {x}": "Fel, koden fick {x}",
  "{s} s on this computer": "{s} s på den här datorn",
  "Saved answers from an earlier run": "Sparade svar från en tidigare körning",
  " or worse": " eller sämre",

  // where the favourites finished
  "Where the favourites finished": "Var favoriterna kom i mål",
  "One flag per leg, placed at the favourite's finishing position. The number on the flag is the leg.":
    "En flagga per avdelning, placerad där favoriten kom i mål. Siffran på flaggan är avdelningen.",
  "Median {x}": "Median {x}",
  "{track}, leg {leg}: {horse}": "{track}, avd {leg}: {horse}",
  " (Harry was wrong here)": " (Harry hade fel här)",
  "DQ": "Disk",
  "4th+": "4:e+",

  // games and legs
  "{date} • {n} legs": "{date} • {n} avdelningar",
  "Favourite won {w} of {n}": "Favoriten vann {w} av {n}",
  "Leg": "Avd",
  "The three favourites, as Harry named them": "De tre favoriterna, enligt Harry",
  "Favourite": "Favorit",
  "Check": "Kontroll",
  "Won": "Vann",
  "Disqualified": "Diskvalificerad",
  "Outside top 3": "Utanför topp 3",
  "All answers match the code": "Alla svar stämmer med koden",
  "Some answers differ from the code": "Några svar skiljer sig från koden",
  "What Harry saw": "Det här såg Harry",
  "Ask Harry about this leg": "Fråga Harry om avdelningen",
  "Tell me about leg {leg} at {track}.": "Berätta om avdelning {leg} på {track}.",
  "Before the race": "Före loppet",
  "Harry only saw the odds": "Harry såg bara oddsen",
  "After the race": "Efter loppet",
  "Harry only saw the result": "Harry såg bara resultatet",
  "Who are the three favourites?": "Vilka är de tre favoriterna?",
  "Where did {horse} finish, and did it win?": "Var kom {horse} i mål, och vann den?",
  "Horse": "Häst",
  "Place": "Plac.",
  "Harry answered": "Harry svarade",
  "Show the exact prompt": "Visa exakt prompt",
  "won": "vann",
  "did not win": "vann inte",
  "The code says the favourites are {names}, and the favourite {result}.": "Koden säger att favoriterna är {names}, och att favoriten {result}.",
  "did not win ({place})": "inte vann ({place})",
  "Saved answer from an earlier run": "Sparat svar från en tidigare körning",
  "Answered in {s} s": "Svarade på {s} s",
  "{n} horses started": "{n} hästar startade",

  // how it works
  "How it works": "Så fungerar det",
  "Five steps, and Harry only ever answers small questions.": "Fem steg, och Harry svarar bara på små frågor.",
  "Fetch": "Hämta",
  "The three most recent finished games from ATG's racing API.": "De tre senaste avgjorda omgångarna från ATG:s API.",
  "Clean": "Rensa",
  "Drop scratched horses, flag disqualified ones and sort each leg by V-odds.":
    "Ta bort strukna hästar, markera diskvalificerade och sortera varje avdelning efter V-odds.",
  "Ask": "Fråga",
  "Harry first sees only the odds and names the favourites. Then it sees only the result and says where the favourite finished.":
    "Harry ser först bara oddsen och namnger favoriterna. Sedan ser Harry bara resultatet och säger var favoriten kom i mål.",
  "Verify": "Kontrollera",
  "Code works out the same answers from the raw data and marks each one.": "Koden räknar fram samma svar ur rådatan och rättar vart och ett.",
  "Count": "Räkna",
  "Code counts the win rate and median from Harry's own answers.": "Koden räknar ut vinstandel och median utifrån Harrys egna svar.",

  // Harry AI
  "New chat": "Ny chatt",
  "Close Harry AI": "Stäng Harry AI",
  "Write to Harry here": "Skriv till Harry här",
  "Your question": "Din fråga",
  "Send": "Skicka",
  "Stop": "Stoppa",
  "Harry AI can be wrong. Fact check important data.": "Harry AI kan ha fel. Faktakolla viktig information.",
  "I answered every leg of the latest {type} games. Ask me about them, or anything about ATG.":
    "Jag har svarat på varje avdelning i de senaste {type}-omgångarna. Fråga mig om dem, eller något om ATG.",
  "Summarise {type}": "Sammanfatta {type}",
  "Biggest upsets": "Största skrällarna",
  "Show leg 1 at {track}": "Visa avdelning 1 på {track}",
  "Compare all game types": "Jämför alla spelformer",
  "Did favourites beat the odds?": "Vann favoriterna oftare än oddsen trodde?",
  "What does V-odds mean?": "Vad betyder V-odds?",
  "Reading your question": "Tolkar fråga", // ATG's own assistant says exactly this
  "Reading the results": "Läser resultaten",
  "Stopped": "Stoppad",

  // Claude mode / Local mode
  "Model": "Modell",
  "Claude mode": "Claude-läge",
  "Local mode": "Lokalt läge",
  "Claude mode only runs on Aria's computer, so the API key stays safe": "Claude-läget körs bara på Arias dator, så att API-nyckeln hålls säker",
  "Pick a game type. Harry AI, running on {model} in the cloud, answers every leg of its three latest games, and plain code checks every answer.":
    "Välj en spelform. Harry AI, som körs på {model} i molnet, svarar på varje avdelning i de tre senaste omgångarna, och vanlig kod kontrollerar varje svar.",
  "Runs on Claude in the cloud": "Körs på Claude i molnet",
  "Claude is not available right now. Switch to Local mode, or check the key in .env.":
    "Claude är inte tillgänglig just nu. Byt till lokalt läge, eller kontrollera nyckeln i .env.",

  // first start (the model download)
  "Getting Harry ready": "Harry gör sig redo",
  "Harry is a small AI model that runs on this computer. The first start downloads it once (about 1.3 GB) and saves it, so after that it starts in seconds.":
    "Harry är en liten AI-modell som körs på den här datorn. Första gången laddas den ner (cirka 1,3 GB) och sparas, så sedan startar den på några sekunder.",
  "Download the model": "Ladda ner modellen",
  "Load it into memory": "Läs in den i minnet",
  "Takes a few seconds": "Tar några sekunder",
  "Answer the latest games": "Svara på de senaste omgångarna",
  "Starts by itself": "Startar av sig själv",
  "Saved on this computer": "Sparad på den här datorn",
  "From Hugging Face: {model}. The terminal shows the progress too.": "Från Hugging Face: {model}. Terminalen visar också hur det går.",
  "Downloading": "Laddar ner",
  "Starting the download": "Startar nedladdningen",
  "{done} of {total} MB": "{done} av {total} MB",
  "No progress for a while. Check the internet connection, it keeps trying by itself.":
    "Inget har hänt på en stund. Kontrollera internetanslutningen, den försöker igen av sig själv.",
  "under a minute left": "under en minut kvar",
  "about {n} min left": "cirka {n} min kvar",

  // footer
  "The favourite is the horse with the lowest final V-odds. A disqualified favourite counts as finishing last. Foreign tracks only publish the top 3, so a finish outside it shows as \"outside top 3\".":
    "Favoriten är hästen med lägst slutligt V-odds. En diskvalificerad favorit räknas som sist i mål. Utländska banor publicerar bara topp 3, så en placering utanför visas som \"utanför topp 3\".",
  "A demo for a code case. Not affiliated with ATG. Race data from ATG's public racing API.":
    "En demo för ett kodcase. Inte kopplad till ATG. Data från ATG:s öppna API.",
};

let lang = savedLanguage();

function savedLanguage() {
  try {
    const saved = localStorage.getItem("lang");
    if (saved === "sv" || saved === "en") return saved;
  } catch {}
  return navigator.language?.startsWith("sv") ? "sv" : "en";
}

function setLanguage(next) {
  lang = next;
  try {
    localStorage.setItem("lang", next);
  } catch {}
  translatePage();
}

function t(text, values = {}) {
  const template = lang === "sv" ? SWEDISH[text] ?? text : text;
  return template.replace(/\{(\w+)\}/g, (_, key) => values[key] ?? "");
}

// Every element marked data-i18n shows its English text in the chosen language
function translatePage() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.dataset.i18n ||= el.textContent.trim().replace(/\s+/g, " "); // remember the English text once
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => (el.placeholder = t(el.dataset.i18nPlaceholder)));
  document.querySelectorAll("[data-i18n-label]").forEach((el) => el.setAttribute("aria-label", t(el.dataset.i18nLabel)));
  document.querySelectorAll(".lang-switch button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.lang === lang));
}

// ---------- numbers, dates and placings ----------

const locale = () => (lang === "sv" ? "sv-SE" : "en-GB");
const odds = (x) => x.toLocaleString(locale(), { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const longDate = (iso) => new Date(iso).toLocaleDateString(locale(), { weekday: "long", day: "numeric", month: "long" });

// 2 -> "2nd" in English, "2:a" in Swedish
function ordinal(n) {
  if (!Number.isInteger(n)) return (Math.round(n * 10) / 10).toLocaleString(locale());
  if (lang === "sv") return `${n}:${[1, 2].includes(n % 10) && ![11, 12].includes(n % 100) ? "a" : "e"}`;
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? "th" : { 1: "st", 2: "nd", 3: "rd" }[n % 10] ?? "th";
  return `${n}${suffix}`;
}
