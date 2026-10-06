// The Harry AI sidebar, styled after ATG's own assistant panel. Harry chats freely and calls
// tools when it needs race data. Nothing is saved anywhere: the page keeps this conversation
// and sends the last few messages with each question. "New chat" clears it.
// Uses helpers from app.js ($, esc, icon, readLines, state) and i18n.js (t, lang, odds).

const HISTORY_SENT = 7; // the last few messages the model sees (odd, so it starts with a question)
const FADE_MS = 600;    // how long a new word takes to fade in
const chat = { history: [], busy: null, tail: null }; // busy: the question being answered, tail: the last request (still sending follow-ups)
const wide = window.matchMedia("(min-width: 1200px)");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)");

function initChat() {
  $("#harry-toggle").addEventListener("click", () => setChatOpen(!document.body.classList.contains("chat-open")));
  $("#chat-close").addEventListener("click", () => setChatOpen(false));
  $("#chat-new").addEventListener("click", newChat);
  $("#chat-input").addEventListener("input", updateSend);
  $("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (chat.busy) chat.busy.abort(); // the button is a stop button while Harry answers
    else askAssistant($("#chat-input").value);
  });
  $("#suggestions").addEventListener("click", (event) => {
    const idea = event.target.closest(".suggestion");
    if (idea) askAssistant(idea.textContent, idea);
  });
  // On narrow screens, a tap on the dark backdrop (the body behind the drawer) closes Harry
  document.body.addEventListener("click", (event) => {
    if (event.target === document.body && !wide.matches) setChatOpen(false);
  });
  setChatOpen(wide.matches);
  newChat();
}

function setChatOpen(open) {
  document.body.classList.toggle("chat-open", open);
  $("#harry-toggle").setAttribute("aria-expanded", open);
  if (open && !wide.matches) $("#chat-input").focus();
}

function newChat() {
  chat.tail?.abort(); // late follow-ups from the last answer must not land in the new chat
  chat.history = [];
  $("#chat-messages").innerHTML = heroHtml();
  $("#suggestions").innerHTML = suggestionsHtml();
  $("#suggestions").hidden = false;
}

// Called by app.js for report events: while nothing has been asked, the empty state and the
// suggestions follow the game type on the page. Harry never asks anything by itself.
function onReport(event) {
  if (event.type === "games" && !chat.history.length && !chat.busy) newChat();
}

// "Ask Harry about this leg" on the report: open the chat and ask about that leg
function askAboutLeg(leg, track) {
  setChatOpen(true);
  askAssistant(t("Tell me about leg {leg} at {track}.", { leg, track }));
}

// ---------- asking ----------

async function askAssistant(question, chip = null) {
  question = question.trim();
  if (!question || chat.busy) return;
  chat.tail?.abort(); // stop waiting for the last answer's follow-ups
  const stop = new AbortController();
  chat.tail = stop;
  setBusy(stop);

  // Ask right away. The answer streams in while the question animates into place.
  const messages = [...chat.history, { role: "user", content: question }].slice(-HISTORY_SENT);
  const request = fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages, game_type: state.type, lang }),
    signal: stop.signal,
  }).catch(() => null);

  $("#chat-input").value = "";
  await showQuestion(question, chip);
  const reply = addReply();

  let answer = "";
  // Runs once: at "done", or when the stream stops early. The follow-up ideas come after "done",
  // so the input is free again while the model is still thinking of them.
  const end = (calls = []) => {
    if (chat.busy !== stop) return;
    reply.finish(stop.signal.aborted);
    if (answer) {
      // Keep the tool calls and their results with the answer, so follow-ups use real data
      chat.history.push({ role: "user", content: question }, { role: "assistant", content: answer.slice(0, 4000), calls });
    }
    setBusy(null);
  };
  try {
    const response = await request;
    if (!response?.ok) throw new Error();
    for await (const event of readLines(response)) {
      if (event.type === "done") end(event.calls);
      else if (event.type === "followups") showFollowUps(event.questions);
      else if (chat.busy === stop) {
        if (event.type === "token") answer += event.text;
        reply.show(event);
      }
    }
  } catch {
    if (chat.busy === stop && !stop.signal.aborted) {
      reply.show({ type: "error", message: t("Lost contact with the app. Check that it is still running.") });
    }
  }
  end();
}

// Ideas for what to ask next, in the docked row where the suggestions were. Asking anything folds them away.
function showFollowUps(questions) {
  const ideas = $("#suggestions");
  if (chat.busy || !questions?.length) return;
  ideas.innerHTML = chipsHtml(questions);
  ideas.hidden = false;
  if (!calm.matches) ideas.animate([{ opacity: 0, transform: "translateY(6px)" }, { opacity: 1, transform: "none" }], { duration: 200, easing: "ease-out" });
  scrollChat();
}

function setBusy(controller) {
  chat.busy = controller;
  $("#chat-send").classList.toggle("stop", Boolean(controller));
  $("#chat-send").setAttribute("aria-label", t(controller ? "Stop" : "Send"));
  $("#chat-send use").setAttribute("href", controller ? "#i-stop" : "#i-send");
  updateSend();
}

// Send is only possible with some text. Stop is always possible.
function updateSend() {
  $("#chat-send").disabled = !chat.busy && !$("#chat-input").value.trim();
}

// The empty state fades out and the suggestions fold away.
// A picked suggestion lifts out and flies into place as the question.
async function showQuestion(question, chip) {
  const list = $("#chat-messages");
  const ideas = $("#suggestions");
  const bubble = document.createElement("div");
  bubble.className = "msg user";
  bubble.textContent = question;
  const time = (ms) => (calm.matches ? 0 : ms);

  let ghost = null;
  if (chip) {
    const box = chip.getBoundingClientRect();
    ghost = chip.cloneNode(true);
    ghost.classList.add("ghost");
    Object.assign(ghost.style, { left: `${box.left}px`, top: `${box.top}px`, width: `${box.width}px`, height: `${box.height}px` });
    document.body.append(ghost);
    chip.style.visibility = "hidden";
  }

  // Every animation keeps its last frame (fill: "forwards"). Without it an element jumps back
  // to where it started for one frame before the code takes over, which looks like a skipped frame.
  const hold = { fill: "forwards" };
  const hero = list.querySelector(".hero");
  const folding = [];
  if (hero) folding.push(hero.animate([{ opacity: 1 }, { opacity: 0, transform: "scale(0.97)" }], { duration: time(200), ...hold }).finished);
  if (!ideas.hidden) {
    ideas.style.overflow = "hidden"; // clip while it shrinks
    folding.push(ideas.animate([{ height: `${ideas.offsetHeight}px`, opacity: 1 }, { height: "0px", opacity: 0, paddingTop: "0px", paddingBottom: "0px" }],
      { duration: time(260), easing: "ease-in", ...hold }).finished);
  }
  await Promise.all(folding);
  hero?.remove();
  ideas.getAnimations().forEach((animation) => animation.cancel());
  ideas.hidden = true;
  ideas.innerHTML = "";

  list.append(bubble);
  scrollChat();
  if (!ghost) {
    bubble.animate([{ opacity: 0, transform: "translateY(10px)" }, { opacity: 1, transform: "none" }],
      { duration: time(240), easing: "ease-out" });
    return;
  }

  // The chip glides with a transform (smooth on every screen) and grows into the bubble's exact
  // size and look, so swapping the ghost for the real bubble at the end is invisible.
  bubble.style.visibility = "hidden";
  const from = ghost.getBoundingClientRect();
  const to = bubble.getBoundingClientRect();
  const end = getComputedStyle(bubble);
  await ghost.animate([
    { transform: "translate(0, 0)", width: `${from.width}px`, height: `${from.height}px` },
    {
      transform: `translate(${to.left - from.left}px, ${to.top - from.top}px)`,
      width: `${to.width}px`, height: `${to.height}px`, padding: end.padding, borderRadius: end.borderRadius,
      background: end.backgroundColor, color: end.color, fontSize: end.fontSize, lineHeight: end.lineHeight,
      letterSpacing: end.letterSpacing,
    },
  ], { duration: time(460), easing: "cubic-bezier(0.22, 1, 0.36, 1)", ...hold }).finished;
  bubble.style.visibility = "";
  ghost.remove();
}

// One answer from Harry. Text, tool steps and tables are added in the order they arrive.
function addReply() {
  const node = document.createElement("div");
  node.className = "msg ai working";
  node.innerHTML = `<span class="orb" aria-hidden="true"></span>
    <div class="msg-body"><p class="thinking">${t("Reading your question")}</p></div>`;
  $("#chat-messages").append(node);
  scrollChat();

  const body = node.querySelector(".msg-body");
  let block = null; // the text being written right now
  let text = "";
  let born = [];    // when each word of that text first appeared

  function render(final) {
    // While streaming, show whole words only, so a half word never pops in
    const cut = final ? text.length : Math.max(text.lastIndexOf(" "), text.lastIndexOf("\n")) + 1;
    let visible = text.slice(0, cut);
    if (!final && (visible.match(/\*\*/g) ?? []).length % 2) visible += "**"; // close a bold still on its way
    block.innerHTML = fadeIn(markdown(visible), born);
  }

  return {
    show(event) {
      body.querySelector(".thinking")?.remove();
      if (event.type === "token") {
        if (!block) {
          block = document.createElement("div");
          block.className = "ai-text";
          body.append(block);
          text = "";
          born = [];
        }
        text += event.text;
        render(false);
      }
      if (event.type === "tool") {
        if (block) render(true);
        block = null; // text after a tool starts a new paragraph block
        body.insertAdjacentHTML("beforeend", `<p class="tool-step">${icon("check")}${esc(event.label)}</p>
          ${event.view ? viewHtml(event.view) : ""}<p class="thinking">${t("Reading the results")}</p>`);
      }
      if (event.type === "error") {
        body.insertAdjacentHTML("beforeend", `<p class="ai-text error">${esc(event.message)}</p>`);
      }
      scrollChat();
    },
    finish(stopped) {
      if (block) render(true);
      body.querySelector(".thinking")?.remove();
      if (stopped) body.insertAdjacentHTML("beforeend", `<p class="note">${t("Stopped")}</p>`);
      node.classList.remove("working");
    },
  };
}

// Wrap each word in a span that fades in from a blur. A word keeps its start time across
// re-renders, so one that is still fading carries on smoothly instead of starting over.
function fadeIn(html, born) {
  const now = performance.now();
  let i = 0;
  return html.split(/(<[^>]+>)/).map((part) => (part.startsWith("<") ? part : part.replace(/\S+/g, (word) => {
    born[i] ??= now;
    const age = Math.round(now - born[i++]);
    return age >= FADE_MS ? word : `<span class="fade" style="animation-delay: -${age}ms">${word}</span>`;
  }))).join("");
}

function scrollChat() {
  const list = $("#chat-messages");
  list.scrollTop = list.scrollHeight;
}

// ---------- pieces of html ----------

// The empty state, like ATG's assistant: orb, name and one line about what to ask
function heroHtml() {
  return `
    <div class="hero">
      <div class="hero-mark"><span class="orb big" aria-hidden="true"></span><span>Harry AI</span></div>
      <p>${esc(t("I answered every leg of the latest {type} games. Ask me about them, or anything about ATG.", { type: state?.type ?? "V85" }))}</p>
    </div>`;
}

// Short commands, like ATG's own suggestion chips
function suggestionsHtml() {
  const type = state?.type ?? "V85";
  const latest = Object.values(state?.games ?? {})[0];
  const ideas = [
    t("Summarise {type}", { type }),
    t("Biggest upsets"),
    latest ? t("Show leg 1 at {track}", { track: latest.track }) : null,
    t("Compare all game types"),
    t("Is the favourite a good bet?"),
    t("What does V-odds mean?"),
  ].filter(Boolean);
  return chipsHtml(ideas);
}

function chipsHtml(ideas) {
  return ideas.map((idea) => `<button type="button" class="suggestion">${esc(idea)}</button>`).join("");
}

// A tool result as an ATG style card: game tag, number badges, leg flags.
// --i numbers the parts top to bottom, so they fade in one after another (style.css).
function viewHtml(view) {
  const first = view.tiles ? 2 : 1; // the row after the caption (and tiles)
  const order = (i) => `style="--i:${Math.min(i, 12)}"`;
  const tiles = view.tiles
    ? `<div class="mini-tiles" ${order(1)}>${view.tiles.map((t) => `<div><span>${esc(t.label)}</span><strong>${esc(t.value)}</strong></div>`).join("")}</div>`
    : "";
  const head = view.columns.map((c) => `<th class="${c.type}">${esc(c.label)}</th>`).join("");
  const rows = view.rows.map((row, i) =>
    `<tr ${order(first + 1 + i)}>${view.columns.map((c) => `<td class="${c.type}">${cellHtml(c.type, row[c.key])}</td>`).join("")}</tr>`).join("");
  const tag = view.game_type ? `<span class="game-tag">${esc(view.game_type)}</span>` : "";
  return `
    <figure class="data-card" ${view.game_type ? `data-game="${esc(view.game_type)}"` : ""}>
      <figcaption>${tag}${esc(view.title)}</figcaption>
      ${tiles}
      <div class="table-scroll"><table><thead><tr ${order(first)}>${head}</tr></thead><tbody>${rows}</tbody></table></div>
    </figure>`;
}

function cellHtml(type, value) {
  if (value === null || value === undefined) return "";
  if (type === "runner") return `<span class="number">${value.number}</span><span class="name">${esc(value.name)}</span>`;
  if (type === "leg") return `<span class="leg-flag">${value.leg}</span><span class="track">${esc(value.track)}</span>`;
  if (type === "odds") return odds(value);
  if (type === "percent") return `${Math.round(value * 100)}<small>%</small>`;
  if (type === "game") return `<span class="game-tag" data-game="${esc(value)}">${esc(value)}</span>`;
  if (type === "finish") {
    if (value === "1") return `<span class="won-flag">${t("Won")}</span>`;
    return `<span class="${value === "disqualified" ? "dq" : ""}">${columnLabel(value)}</span>`;
  }
  return esc(value);
}

// Just enough markdown for chat answers: paragraphs, lists, **bold** and `code`. HTML is escaped first.
function markdown(text) {
  const inline = (line) => esc(line)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>");
  const html = [];
  let list = null;
  for (const line of text.split("\n")) {
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)$/);
    if (item) {
      (list ??= []).push(`<li>${inline(item[1])}</li>`);
      continue;
    }
    if (list) html.push(`<ul>${list.join("")}</ul>`);
    list = null;
    const heading = line.match(/^#{1,6}\s+(.*)$/);
    if (heading) html.push(`<p><strong>${inline(heading[1])}</strong></p>`);
    else if (line.trim()) html.push(`<p>${inline(line)}</p>`);
  }
  if (list) html.push(`<ul>${list.join("")}</ul>`);
  return html.join("");
}

initChat();
