// The Harry AI sidebar, styled after ATG's own assistant panel. Harry AI chats freely and calls
// tools when it needs race data. Nothing is saved anywhere: the page keeps this conversation
// and sends the last few messages with each question. "New chat" clears it.
// Uses helpers from app.js ($, esc, icon, readLines, errorText, columnLabel, state, mode) and
// i18n.js (t, lang, odds). app.js calls newChat (mode switch) and askAboutLeg (the leg button).

const HISTORY_SENT = 7; // the last few messages the model sees (odd, so it starts with a question)
const FADE_MS = 600;    // how long a new word takes to fade in
const LOOK_MS = 900;    // the shortest time a "Looking at ..." status shows, so it can be read
const FOLLOW_LAG = 12;  // how far (px) the thread may trail its bottom while it glides there
const chat = { history: [], busy: null, tail: null }; // busy: the question being answered, tail: the last request (still sending follow-ups)
const follow = { pinned: true, wrote: 0, frame: 0, until: 0 }; // the thread keeps to its bottom while pinned (scrollChat)
const wide = window.matchMedia("(min-width: 1200px)");
const calm = window.matchMedia("(prefers-reduced-motion: reduce)");

function initChat() {
  $("#harry-toggle").addEventListener("click", () => setChatOpen(!document.body.classList.contains("chat-open")));
  $("#chat-close").addEventListener("click", () => setChatOpen(false));
  $("#chat-new").addEventListener("click", newChat);
  $("#chat-input").addEventListener("input", updateSend);
  // Scrolling up to read stops the thread from following new text, scrolling back down starts it again
  const list = $("#chat-messages");
  list.addEventListener("wheel", (event) => event.deltaY < 0 && list.scrollTop > 0 && (follow.pinned = false), { passive: true });
  list.addEventListener("scroll", () => {
    const top = list.scrollTop;
    if (Math.abs(top - follow.wrote) > 1) { // the user scrolled, not the glide
      const gap = list.scrollHeight - list.clientHeight - top;
      follow.pinned = gap < 1 || (top > follow.wrote && gap < 40);
    }
    follow.wrote = top;
  });
  $("#chat-form").addEventListener("submit", (event) => {
    event.preventDefault();
    if (chat.busy) chat.busy.abort(); // the button is a stop button while Harry AI answers
    else askAssistant($("#chat-input").value);
  });
  $("#suggestions").addEventListener("click", (event) => {
    const idea = event.target.closest(".suggestion");
    if (idea) askAssistant(idea.textContent, idea);
  });
  // On narrow screens, a tap on the dark backdrop (the body behind the drawer) closes Harry AI
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
  chat.tail?.abort(); // stop the last answer and its follow-ups, so nothing late lands in the new chat
  setBusy(null);
  chat.history = [];
  follow.pinned = true;
  $("#chat-messages").innerHTML = heroHtml();
  $("#suggestions").innerHTML = suggestionsHtml();
  $("#suggestions").hidden = false;
}

// Called by app.js for report events: while nothing has been asked, the empty state and the
// suggestions follow the game type on the page. Harry AI never asks anything by itself.
function onReport(event) {
  if (event.type === "games" && !chat.history.length && !chat.busy) newChat();
}

// "Ask Harry AI about this leg" on the report: open the chat and ask about that leg
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
    body: JSON.stringify({ messages, game_type: state.type, lang, mode }),
    signal: stop.signal,
  }).catch(() => null);

  $("#chat-input").value = "";
  follow.pinned = true; // a new question always brings the thread back down
  await showQuestion(question, chip, stop.signal);
  if (chat.busy !== stop) return; // "New chat" (or a mode switch) came during the animation
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
    if (!response) throw new Error();
    if (!response.ok) { // the app answered but refused (for example a too long conversation)
      reply.show({ type: "error", code: "failed" });
      return end();
    }
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
  unfold(ideas); // the row opens its space, so the thread above glides up instead of jumping
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
async function showQuestion(question, chip, signal) {
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
    const height = ideas.offsetHeight; // as it is now, also halfway through opening
    ideas.getAnimations().forEach((animation) => animation.cancel()); // a row still opening stops, so it cannot undo the clip (unfold)
    ideas.style.overflow = "hidden"; // clip while it shrinks
    folding.push(ideas.animate([{ height: `${height}px`, opacity: 1 }, { height: "0px", opacity: 0, paddingTop: "0px", paddingBottom: "0px" }],
      { duration: time(260), easing: "ease-in", ...hold }).finished);
  }
  await Promise.all(folding);
  if (signal.aborted) return ghost?.remove(); // a new chat started meanwhile: leave it alone
  hero?.remove();
  ideas.getAnimations().forEach((animation) => animation.cancel());
  ideas.hidden = true;
  ideas.innerHTML = "";

  list.append(bubble);
  scrollChat(Boolean(ghost)); // the chip flies to where the bubble ends up, so the thread must be there already
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

// One answer from Harry AI. Text, tool steps and tables are added in the order they arrive, above
// a status line that says what Harry AI is doing until the answer text starts.
function addReply() {
  const node = document.createElement("div");
  node.className = "msg ai working";
  node.innerHTML = `<span class="orb" aria-hidden="true"></span><div class="msg-body"></div>`;
  $("#chat-messages").append(node);

  const body = node.querySelector(".msg-body");
  const status = statusLine(body);
  status.show(t("Thinking")); // at once, before the server says anything
  let block = null; // the text being written right now
  let text = "";
  let born = [];    // when each word of that text first appeared

  function render(final) {
    // While streaming, show whole words only, so a half word never pops in
    const cut = final ? text.length : Math.max(text.lastIndexOf(" "), text.lastIndexOf("\n")) + 1;
    let visible = text.slice(0, cut);
    if (!final && (visible.match(/\*\*/g) ?? []).length % 2) visible += "**"; // close a bold still on its way
    block.innerHTML = fadeIn(markdown(visible), born);
    // The block joins the thread with its first whole word. Before that (a half word, a bare "- ")
    // it would still be a part above the status line, and push it down (style.css .msg-body > * + *).
    if (!block.isConnected && block.textContent.trim()) status.line.before(block);
  }

  // New parts go above the status line. A tool step and its card open their space smoothly.
  function add(html, opening) {
    const parts = document.createElement("template");
    parts.innerHTML = html;
    const added = [...parts.content.children];
    status.line.before(...added);
    if (opening) added.forEach(unfold);
  }

  return {
    show(event) {
      if (event.type === "status") status.show(event.text || t("Thinking"), event.state === "looking" ? LOOK_MS : 0);
      if (event.type === "token") {
        if (!block) {
          block = document.createElement("div");
          block.className = "ai-text";
          text = "";
          born = [];
        }
        text += event.text;
        render(false);
        if (block.textContent.trim()) status.hide(); // the first word takes the status line's place, at the same height
      }
      if (event.type === "tool") {
        if (block) render(true);
        block = null; // text after a tool starts a new paragraph block
        add(`<p class="tool-step">${icon("check")}${esc(event.label)}</p>${event.view ? viewHtml(event.view) : ""}`, true);
        status.show(t("Thinking")); // the model reads the result next (the server may also say so)
      }
      if (event.type === "error") {
        status.hide();
        add(`<p class="ai-text error">${esc(errorText(event))}</p>`);
      }
      scrollChat();
    },
    finish(stopped) {
      if (block) render(true);
      // What came last takes the status line's place. With nothing to take it, the line folds away.
      status.hide(!stopped && !block?.textContent.trim());
      if (stopped) add(`<p class="note">${t("Stopped")}</p>`);
      node.classList.remove("working");
      scrollChat(); // the last word (held back while streaming) or the note may need room below
    },
  };
}

// The status line under an answer: "Thinking…" while the model works, "Looking at leg 1 at Boden…"
// while a tool runs (the server sends both as status events). A new label fades in as the old one
// fades out, on the same single line, so the thread never moves. A "Looking at" label stays at least
// LOOK_MS so it can be read, but answer text never waits for it: it hides the line at once.
function statusLine(body) {
  const line = document.createElement("p");
  line.className = "status-line";
  line.hidden = true;
  body.append(line);
  let queue = []; // labels waiting for the one on show to have had its time
  let until = 0;  // when the label on show may give way
  let timer = 0;

  function write(text) {
    const old = line.querySelector("span:not(.gone)");
    if (!line.hidden && old?.textContent === text) return;
    const label = document.createElement("span");
    label.textContent = text; // the server's text can hold a name the model wrote, so never as HTML
    if (line.hidden) {
      line.replaceChildren(label);
      line.hidden = false;
      return unfold(line);
    }
    line.append(label);
    if (!old) return;
    if (calm.matches) return old.remove();
    label.className = "next"; // fades in once the old label has gone (style.css)
    old.className = "gone";
    old.setAttribute("aria-hidden", "true");
    old.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 150, easing: "ease-in", fill: "forwards" })
      .finished.then(() => old.remove(), () => {});
  }

  function next() {
    clearTimeout(timer);
    const wait = until - performance.now();
    if (wait > 0) return void (timer = setTimeout(next, wait));
    const label = queue.shift();
    if (!label) return;
    write(`${label.text}…`);
    until = performance.now() + label.hold;
    if (queue.length) timer = setTimeout(next, label.hold);
  }

  return {
    line,
    show(text, hold = 0) {
      queue = [...queue.filter((label) => label.hold), { text, hold }]; // a waiting "Thinking" gives way to the newer label
      next();
    },
    hide(fold = false) {
      clearTimeout(timer);
      queue = [];
      until = 0;
      if (line.hidden) return;
      if (!fold || calm.matches) return void (line.hidden = true);
      line.style.overflow = "hidden";
      const { height, marginTop } = getComputedStyle(line);
      const closing = line.animate([{ height, marginTop }, { height: "0px", marginTop: "0px" }], { duration: 200, easing: "ease", fill: "forwards" });
      closing.finished.then(() => {
        line.hidden = true;
        line.style.overflow = "";
        closing.cancel();
      }, () => {});
    },
  };
}

// A new part of the thread opens its space: it grows from nothing to its height (and its gap
// above), so whatever is below glides down and the thread follows, instead of everything jumping
function unfold(part) {
  if (!calm.matches && part.isConnected) {
    const { height, marginTop, paddingTop, paddingBottom } = getComputedStyle(part);
    const ms = Math.min(600, 200 + part.offsetHeight * 0.6); // a taller part takes a little longer
    part.style.overflow = "hidden";
    // Cancelled (the follow-up row folding away while it opens): the fold keeps the clip, so leave it
    part.animate([
      { height: "0px", marginTop: "0px", paddingTop: "0px", paddingBottom: "0px" },
      { height, marginTop, paddingTop, paddingBottom },
    ], { duration: ms, easing: "ease" }).finished.then(() => (part.style.overflow = ""), () => {});
    follow.until = Math.max(follow.until, performance.now() + ms);
  }
  scrollChat();
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

// Keep the newest part of the thread in view while the user is at the bottom. It glides there
// instead of jumping (instant: at once, for the flying chip and reduced motion).
function scrollChat(instant = false) {
  if (!follow.pinned) return;
  if (!instant && !calm.matches) return void (follow.frame ||= requestAnimationFrame(glide));
  const list = $("#chat-messages");
  list.scrollTop = list.scrollHeight;
  follow.wrote = list.scrollTop;
}

// One frame of gliding: part of the way down, so a new line or bubble eases into view. While a
// part opens, never more than FOLLOW_LAG behind, so it is followed frame by frame.
// Steps are whole pixels: Safari drops the fraction of a scrollTop write, so a step under 1px would
// never arrive. A frame that cannot move the thread is at its bottom, so the glide stops there.
function glide() {
  const list = $("#chat-messages");
  const before = list.scrollTop;
  const left = list.scrollHeight - list.clientHeight - before;
  const opening = performance.now() < follow.until;
  if (follow.pinned && left > 0) {
    const step = Math.ceil(Math.max(left * 0.3, opening ? left - FOLLOW_LAG : 0));
    list.scrollTop = left < 2 ? list.scrollHeight : before + step;
    if (list.scrollTop === before) list.scrollTop = list.scrollHeight; // the engine rounded the step away: go to the bottom
    follow.wrote = list.scrollTop;
  }
  const moved = list.scrollTop !== before;
  follow.frame = follow.pinned && ((left >= 2 && moved) || opening) ? requestAnimationFrame(glide) : 0;
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
    t("Did favourites beat the odds?"),
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
    ? `<div class="mini-tiles" ${order(1)}>${view.tiles.map((t) => `<div><span>${esc(t.label)}</span><strong>${rolling(t.value)}</strong></div>`).join("")}</div>`
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

// Digits that roll up from 0 like a counter (style.css .roll): each digit is a column of 0 to 9 over
// an invisible copy of the real digit, which keeps the width and the line. Screen readers get the plain text.
function rolling(text) {
  const digits = [...String(text)].map((c) => (/[0-9]/.test(c)
    ? `<span class="roll"><i>${c}</i><span style="--d:${c}">0<br>1<br>2<br>3<br>4<br>5<br>6<br>7<br>8<br>9</span></span>`
    : esc(c))).join("");
  return `<span class="sr-only">${esc(text)}</span><span aria-hidden="true">${digits}</span>`;
}

function cellHtml(type, value) {
  if (value === null || value === undefined) return "";
  if (type === "runner") return `<span class="number">${value.number}</span><span class="name">${esc(value.name)}</span>`;
  if (type === "leg") return `<span class="leg-flag">${value.leg}</span><span class="track">${esc(value.track)}</span>`;
  if (type === "odds") return odds(value);
  if (type === "percent") return `${rolling(Math.round(value * 100))}<small>%</small>`;
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
