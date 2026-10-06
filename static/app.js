// The page: pick a game type, stream the report, draw each leg as it arrives.
// Text goes through t() from i18n.js, so the page works in English and Swedish.

const GAME_TYPES = ["V85", "V86", "GS75", "V64", "V65", "V5", "V4", "V3", "dd", "ld"];
const FULL_NAMES = { dd: "Dagens Dubbel", ld: "Lunchdubbel" };

const $ = (selector) => document.querySelector(selector);
let running = null; // AbortController for the report being streamed, so we can cancel it
let state = null;   // everything we know about the current report

// ---------- start ----------

function init() {
  translatePage();
  $("#game-types").innerHTML = GAME_TYPES.map((type) => `
    <button class="game-type" data-game="${type}" type="button">
      ${type}${FULL_NAMES[type] ? ` <small>${FULL_NAMES[type]}</small>` : ""}
    </button>`).join("");
  $("#game-types").addEventListener("click", (event) => {
    const button = event.target.closest(".game-type");
    if (button) load(button.dataset.game);
  });
  // "Ask Harry about this leg" opens the chat with that leg (chat.js)
  $("#games").addEventListener("click", (event) => {
    const button = event.target.closest(".ask-harry");
    if (button) askAboutLeg(Number(button.dataset.leg), button.dataset.track);
  });
  // Switching language redraws the report (its answers are saved, so this is instant)
  $(".lang-switch").addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (button && button.dataset.lang !== lang) {
      setLanguage(button.dataset.lang);
      load(state.type);
    }
  });
  checkModel();
  load("V85");
}

// Only says something while the local model is still starting (the very first start downloads it)
async function checkModel() {
  let status = { llm: "offline", model: "" };
  try {
    status = await (await fetch("/api/status")).json();
  } catch {}
  $("#model-notice").hidden = status.llm === "ready";
  if (status.model) $("#model-name").textContent = shortModel(status.model);
  if (status.llm !== "ready") setTimeout(checkModel, 3000);
}

// ---------- streaming ----------

async function load(type) {
  running?.abort();
  running = new AbortController();
  state = { type, games: {}, legsTotal: 0, legs: [], right: 0, checked: 0, wins: 0 };

  document.body.dataset.game = type;
  document.querySelectorAll(".game-type").forEach((b) => b.classList.toggle("active", b.dataset.game === type));
  $("#title-type").textContent = type;
  $("#title-name").textContent = FULL_NAMES[type] ?? "";
  $("#fact-games").innerHTML = SKELETON;
  $("#fact-legs").innerHTML = SKELETON;
  $("#games").innerHTML = `<div class="skeleton game-skeleton"></div>`.repeat(3); // shaped like the real blocks
  $("#message").hidden = true;
  resetAnswers();
  drawFinishes();
  setProgress(t("Fetching the latest games from ATG"));

  try {
    const response = await fetch(`/api/report/${type}`, { signal: running.signal });
    for await (const event of readLines(response)) handle(event);
  } catch (error) {
    if (error.name !== "AbortError") showMessage(t("Lost contact with the app. Check that it is still running."));
  }
}

// The API sends one JSON object per line
async function* readLines(response) {
  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    const lines = buffer.split("\n");
    buffer = lines.pop();
    for (const line of lines) if (line) yield JSON.parse(line);
  }
}

function handle(event) {
  if (event.type === "games") showGames(event);
  if (event.type === "leg") showLeg(event);
  if (event.type === "summary") showSummary(event);
  if (event.type === "error") showMessage(errorText(event));
  globalThis.onReport?.(event); // lets the Harry AI sidebar (chat.js) react to the report
}

// The server sends a short error code, the page says it in its own language
function errorText(event) {
  const texts = {
    no_games: t("ATG has no finished {type} games right now.", { type: state.type }),
    model_not_ready: t("The local model is not ready yet. It may still be downloading or loading."),
    atg_unavailable: t("Could not get data from ATG right now. Please try again in a moment."),
    failed: t("Something went wrong. Please try again."),
  };
  return texts[event.code] ?? event.message;
}

// ---------- events ----------

function showGames(event) {
  state.legsTotal = event.games.reduce((sum, game) => sum + game.legs, 0);
  event.games.forEach((game) => (state.games[game.id] = game));
  $("#fact-games").textContent = event.games.length;
  $("#fact-legs").textContent = state.legsTotal;
  $("#model-name").textContent = shortModel(event.model);

  $("#games").innerHTML = event.games.map((game) => `
    <article class="game" id="game-${game.id}">
      <header class="game-head">
        <h3>${esc(game.track)}</h3>
        <span class="meta">${t("{date} • {n} legs", { date: longDate(game.start), n: game.legs })}</span>
        <span class="score"></span>
      </header>
      <div class="leg-header" aria-hidden="true">
        <span>${t("Leg")}</span><span>${t("The three favourites, as Harry named them")}</span>
        <span>${t("Favourite")}</span><span>${t("Check")}</span>
      </div>
      <div class="legs"></div>
    </article>`).join("");
  setProgress(t("Harry is answering leg {n} of {total}", { n: 1, total: state.legsTotal }));
}

function showLeg(event) {
  state.legs.push(event);
  const checks = Object.values(event.checks);
  state.checked += checks.length;
  state.right += checks.filter(Boolean).length;
  state.wins += event.llm.won ? 1 : 0;

  const game = document.getElementById(`game-${event.game}`);
  game.querySelector(".legs").insertAdjacentHTML("beforeend", legHtml(event));
  const legsShown = state.legs.filter((leg) => leg.game === event.game);
  const wins = legsShown.filter((leg) => leg.llm.won).length;
  game.querySelector(".score").textContent = t("Favourite won {w} of {n}", { w: wins, n: legsShown.length });

  drawFinishes(undefined, true);
  showLegAnswers();
  const done = state.legs.length;
  setProgress(done < state.legsTotal ? t("Harry is answering leg {n} of {total}", { n: done + 1, total: state.legsTotal }) : t("Counting"));
}

function showSummary(event) {
  const { llm, truth, checks } = event;
  const median = medianText(llm);
  setAnswer("median", median,
    Number.isInteger(llm.median) && llm.median_exact ? t("Half of the favourites finished {x} or better", { x: median }) : "",
    checks.median ? [true, t("Code agrees")] : [false, t("Wrong, code got {x}", { x: medianText(truth) })]);
  setAnswer("rate", t("{a} of {b} ({pct})", { a: llm.wins, b: llm.legs, pct: percent(llm.win_rate) }),
    t("The odds gave it a {x} chance", { x: percent(event.odds_win_rate) }),
    checks.wins ? [true, t("Code agrees")] : [false, t("Wrong, code counted {n}", { n: truth.wins })]);
  const fresh = state.legs.some((leg) => !leg.cached);
  const time = fresh ? t("{s} s on this computer", { s: event.seconds }) : t("Saved answers from an earlier run");
  $("#answers-score").textContent = `${t("{right} of {checked} answers right, checked by code", { right: state.right, checked: state.checked })} • ${time}`;
  drawFinishes(llm.median);
  setProgress("");
}

function showMessage(text) {
  $("#message").textContent = text;
  $("#message").hidden = false;
  setProgress("");
}

// ---------- one leg ----------

function legHtml(event) {
  const byName = Object.fromEntries(event.runners.map((r) => [r.name, r]));
  const allRight = Object.values(event.checks).every(Boolean);

  const picks = event.llm.favourites.map((name, i) => {
    const r = byName[name];
    const share = r.bet_share === null ? "" : ` • ${state.type} ${Math.round(r.bet_share)}<small>%</small>`;
    return `<li class="pick ${i === 0 ? "first" : ""}">
      <span class="number">${r.number}</span>
      <span class="pick-text"><span class="name">${esc(r.name)}</span>
      <span class="odds">V-odds ${odds(r.odds)}${share}</span></span>
    </li>`;
  }).join("");

  const position = event.llm.position;
  const result = event.llm.won
    ? `<span class="result won">${t("Won")}</span>`
    : `<span class="result ${{ disqualified: "dq", unplaced: "outside" }[position] ?? ""}">${finishText(position)}</span>`;

  const truth = event.truth;
  const truthResult = truth.won ? t("won") : t("did not win ({place})", { place: finishText(truth.position).toLowerCase() });
  const correction = allRight ? "" : `<p class="correction">${icon("cross")}<span>${t(
    "The code says the favourites are {names}, and the favourite {result}.",
    { names: `<strong>${esc(truth.favourites.join(", "))}</strong>`, result: `<strong>${truthResult}</strong>` })}</span></p>`;

  return `
    <details class="leg ${allRight ? "right" : "wrong"}">
      <summary>
        <span class="leg-flag">${event.leg}</span>
        <ol class="picks">${picks}</ol>
        ${result}
        <span class="verdict" title="${t(allRight ? "All answers match the code" : "Some answers differ from the code")}">
          ${icon(allRight ? "check" : "cross")}
        </span>
        ${icon("chevron")}
      </summary>
      <div class="leg-detail">
        <div class="detail-head">
          <h4>${t("What Harry saw")}</h4>
          <button class="ask-harry" type="button" data-leg="${event.leg}" data-track="${esc(state.games[event.game].track)}">
            <span class="orb" aria-hidden="true"></span>${t("Ask Harry about this leg")}
          </button>
        </div>
        ${correction}
        ${stepsHtml(event)}
        <p class="timing">${event.cached ? t("Saved answer from an earlier run") : t("Answered in {s} s", { s: event.seconds })}
          • ${t("{n} horses started", { n: event.runners.length })}</p>
      </div>
    </details>`;
}

// What Harry saw, as two cards: before the race (only the odds) and after the race (only the result).
// The boards hold the same data as the prompts, drawn as tables. The exact prompt is one click away.
function stepsHtml(event) {
  const picked = new Set(event.llm.favourites);
  const favourite = event.llm.favourites[0];
  const board = event.runners.map((r, i) => `
    <tr class="${picked.has(r.name) ? "picked" : ""}"><td class="rank">${i + 1}</td><td>${esc(r.name)}</td><td class="num">${odds(r.odds)}</td></tr>`).join("");
  const result = [...event.runners].sort((a, b) => finishOrder(a.finish) - finishOrder(b.finish)).map((r) => `
    <tr class="${r.name === favourite ? "picked" : ""}"><td class="rank">${columnLabel(r.finish)}</td><td>${esc(r.name)}</td></tr>`).join("");

  const card = (letter, title, note, task, head, rows, answer, ok, prompt) => `
    <div class="step-card">
      <div class="step-head"><span class="step-letter">${letter}</span><div><strong>${title}</strong><small>${note}</small></div></div>
      <p class="task">${task}</p>
      <div class="board-scroll"><table class="board"><thead><tr>${head}</tr></thead><tbody>${rows}</tbody></table></div>
      <p class="harry-said"><span class="orb" aria-hidden="true"></span><span>${t("Harry answered")} <strong>${answer}</strong></span>${mark(ok)}</p>
      <details class="raw"><summary>${icon("chevron")}${t("Show the exact prompt")}</summary><pre>${esc(prompt)}</pre></details>
    </div>`;

  return `<div class="steps-grid">
    ${card("A", t("Before the race"), t("Harry only saw the odds"), t("Who are the three favourites?"),
      `<th>#</th><th>${t("Horse")}</th><th class="num">V-odds</th>`, board,
      esc(event.llm.favourites.join(", ")), event.checks.favourites, event.prompts[0])}
    ${card("B", t("After the race"), t("Harry only saw the result"), t("Where did {horse} finish, and did it win?", { horse: esc(favourite) }),
      `<th>${t("Place")}</th><th>${t("Horse")}</th>`, result,
      `${esc(finishText(event.llm.position))}, ${event.llm.won ? t("won") : t("did not win")}`,
      event.checks.position && event.checks.won, event.prompts[1])}
  </div>`;
}

function finishOrder(finish) {
  if (/^\d+$/.test(finish)) return Number(finish);
  return finish === "unplaced" ? 900 : 999;
}

// ---------- where the favourites finished ----------

// One small leg flag per leg, in the column of the favourite's finishing position
function drawFinishes(median, animateLast = false) {
  const legs = state.legs;
  const positions = legs.map((leg) => leg.llm.position);
  const placed = positions.filter((p) => /^\d+$/.test(p)).map(Number);
  const columns = [...Array(Math.max(5, ...placed)).keys()].map((i) => String(i + 1));
  if (positions.includes("unplaced")) columns.push("unplaced");
  if (positions.includes("disqualified")) columns.push("disqualified");

  $("#finishes").style.setProperty("--columns", columns.length);
  $("#finishes").innerHTML = columns.map((column) => {
    const flags = legs.map((leg, i) => {
      if (leg.llm.position !== column) return "";
      const right = Object.values(leg.checks).every(Boolean);
      const isNew = animateLast && i === legs.length - 1;
      const tip = t("{track}, leg {leg}: {horse}", { track: state.games[leg.game].track, leg: leg.leg, horse: leg.llm.favourites[0] })
        + (right ? "" : t(" (Harry was wrong here)"));
      return `<span class="dot ${right ? "" : "off"} ${isNew ? "new" : ""}" title="${esc(tip)}">${leg.leg}</span>`;
    }).join("");
    return `<div class="column ${column === "1" ? "win" : ""}">
      <div class="dots">${flags}</div>
      <span class="label">${columnLabel(column)}</span>
    </div>`;
  }).join("");

  const marker = $("#median-marker");
  marker.hidden = median === undefined;
  if (median !== undefined) {
    const at = Math.min((median - 0.5) / columns.length, 1);
    marker.style.setProperty("--at", at);
    marker.querySelector("span").textContent = t("Median {x}", { x: ordinal(median) });
  }
}

// ---------- small helpers ----------

// ---------- Harry's answers to the four questions ----------

function resetAnswers() {
  ["favourites", "won", "median", "rate"].forEach((name) => setAnswer(name, null));
  $("#answers-score").innerHTML = SKELETON;
}

// Questions 1 and 2 are answered per leg, so they fill in while Harry works
function showLegAnswers() {
  const legs = state.legs;
  const count = (key) => legs.filter((leg) => leg.checks[key]).length;
  const status = (right) => [right === legs.length, t("{k} of {n} right", { k: right, n: legs.length })];
  setAnswer("favourites", t("All {n} legs", { n: legs.length }),
    `<a href="#games">${t("See every leg below")}</a>`, status(count("favourites")));
  setAnswer("won", t("Won {w}, lost {l}", { w: state.wins, l: legs.length - state.wins }), "", status(count("won")));
  $("#answers-score").textContent = t("{right} of {checked} answers right, checked by code", { right: state.right, checked: state.checked });
}

// value null shows a loading skeleton. check is [ok, text].
function setAnswer(name, value, note = "", check = null) {
  const row = $(`#answer-${name}`);
  row.querySelector(".a").innerHTML = value === null ? SKELETON : `<strong>${esc(value)}</strong>${note ? `<small>${note}</small>` : ""}`;
  const mark = row.querySelector(".check");
  mark.className = `check ${check ? (check[0] ? "ok" : "bad") : ""}`;
  mark.innerHTML = check ? `${icon(check[0] ? "check" : "cross")}${esc(check[1])}` : "";
}

function setProgress(text) {
  $("#progress").textContent = text;
  $("#progress").hidden = !text;
}

function finishText(position) {
  if (position === "disqualified") return t("Disqualified");
  if (position === "unplaced") return t("Outside top 3");
  return ordinal(Number(position));
}

function columnLabel(column) {
  return { disqualified: t("DQ"), unplaced: t("4th+") }[column] ?? ordinal(Number(column));
}

function medianText(summary) {
  return `${ordinal(summary.median)}${summary.median_exact ? "" : t(" or worse")}`;
}

const SKELETON = `<span class="skeleton"></span>`;
const percent = (x) => `${Math.round(x * 100)}%`;
const icon = (name) => `<svg class="icon icon-${name}" aria-hidden="true"><use href="#i-${name}"></use></svg>`;
const mark = (ok) => `<span class="${ok ? "ok" : "bad"}">${icon(ok ? "check" : "cross")}</span>`;

// "unsloth/Qwen3.5-2B-GGUF:Q4_K_M" -> "Qwen 3.5 2B"
function shortModel(id) {
  const match = id.match(/Qwen([\d.]+)-(\d+B)/i);
  return match ? `Qwen ${match[1]} ${match[2]}` : id;
}

function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

init();
