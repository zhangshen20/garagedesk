/** The voice the owner hears.
 *
 * The server makes the audio (Kokoro, a natural neural voice) one sentence at a
 * time, so the first sentence plays while the rest are still being made, and every
 * browser on every phone sounds the same: Safari, Chrome on iPhone, Android. If the
 * server voice is off or fails, the browser's own best English voice says it.
 *
 * Phones only play sound a page started after a tap: unlockSpeech() must run inside
 * the tap that starts listening (or any tap), then speak() works for the rest of the
 * visit, including news that arrives later ("Jenny approved the Corolla"). */

let serverVoice = true;
let audio: HTMLAudioElement | null = null;
let turn = 0;
let unlocked = false;

// a valid, empty WAV: playing it inside a tap unlocks the audio element on iOS
const SILENT = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

export function plain(text: string): string {
  return text.replace(/[*_`#>]/g, "").replace(/\s+/g, " ").trim();
}

/** The server's /api/owner/today says whether its voice is on. */
export function setServerVoice(on: boolean) {
  serverVoice = on;
}

function element(): HTMLAudioElement {
  if (!audio) {
    audio = new Audio();
    audio.preload = "auto";
    audio.setAttribute("playsinline", "");
  }
  return audio;
}

/** iOS 17+ audio session. "playback" plays through the ringer switch like a voice
 * memo, but it forbids the microphone: getUserMedia then fails with InvalidStateError
 * (seen live on every iPhone press). Recording needs "play-and-record". */
export function setAudioSession(type: "playback" | "play-and-record" | "auto") {
  try {
    const session = (navigator as Navigator & { audioSession?: { type: string } }).audioSession;
    if (session && session.type !== type) session.type = type;
  } catch {
    /* older browsers */
  }
}

/** Call inside a tap. Lets the page talk later; says nothing. */
export function unlockSpeech(recordingNext = false) {
  setAudioSession(recordingNext ? "play-and-record" : "playback");
  if (!unlocked) {
    try {
      const a = element();
      a.src = SILENT;
      void a.play().then(
        () => (unlocked = true),
        () => undefined,
      );
    } catch {
      /* ignore */
    }
  }
  try {
    window.speechSynthesis?.speak(new SpeechSynthesisUtterance(""));
  } catch {
    /* no browser voice: the server voice or the screen will do */
  }
}

/** Stop talking now (he tapped to talk, or a new answer came in). */
export function stopSpeech() {
  turn++;
  try {
    audio?.pause();
  } catch {
    /* ignore */
  }
  try {
    window.speechSynthesis?.cancel();
  } catch {
    /* ignore */
  }
}

/** Same split as the server (app/voice/spoken.py sentences), so its cache hits.
 * Long runs without a full stop are cut at commas: the server takes 400 characters. */
export function sentences(text: string): string[] {
  const out: string[] = [];
  for (const line of text.split(/\n+/)) {
    // no lookbehind: older iPhones' Safari can't parse it
    for (const s of plain(line).replace(/([.?!])\s+/g, "$1\u0000").split("\u0000")) {
      if (!s) continue;
      if (s.length <= 380) out.push(s);
      else out.push(...(s.match(/[^,;]{1,380}[,;]?\s*/g) ?? []).map((p) => p.trim()).filter(Boolean));
    }
  }
  return out;
}

/** Say it. Resolves when finished or interrupted. */
export async function speak(text: string): Promise<void> {
  stopSpeech();
  const mine = turn;
  const parts = sentences(text);
  if (!parts.length) return;
  if (!serverVoice) return browserSay(parts.join(" "), mine);
  // ask for every sentence at once: the server makes them in order and the first is
  // ready soonest; the rest are usually done before the one before them finishes
  const clips = parts.map((p) =>
    fetch(`/api/tts?t=${encodeURIComponent(p)}`).then((r) => {
      if (r.status === 503) serverVoice = false;
      if (!r.ok) throw new Error(`tts ${r.status}`);
      return r.blob();
    }),
  );
  clips.forEach((c) => c.catch(() => undefined));
  for (let i = 0; i < parts.length; i++) {
    let clip: Blob;
    try {
      clip = await clips[i];
    } catch {
      if (mine === turn) await browserSay(parts.slice(i).join(" "), mine);
      return;
    }
    if (mine !== turn) return;
    const ok = await play(clip, mine);
    if (!ok) {
      if (mine === turn) await browserSay(parts.slice(i).join(" "), mine);
      return;
    }
  }
}

function play(clip: Blob, mine: number): Promise<boolean> {
  return new Promise((resolve) => {
    const a = element();
    const url = URL.createObjectURL(clip);
    let settled = false;
    const done = (ok: boolean) => {
      if (settled) return;
      settled = true;
      a.onended = a.onerror = a.onpause = null;
      clearInterval(watch);
      URL.revokeObjectURL(url);
      resolve(ok);
    };
    // interrupted by stopSpeech(): finish quietly
    const watch = setInterval(() => mine !== turn && done(true), 100);
    a.onended = () => done(true);
    a.onerror = () => done(false);
    a.onpause = () => {
      if (mine !== turn || a.ended) done(true);
    };
    a.src = url;
    a.play().then(
      () => (unlocked = true),
      () => done(false), // the phone wouldn't play it: let the browser voice try
    );
  });
}

// --- the browser's own voice, as a fallback ------------------------------------------

const NOVELTY = /albert|bad news|bahh|bells|boing|bubbles|cellos|good news|jester|organ|superstar|trinoids|whisper|wobble|zarvox|fred|junior|ralph|kathy|grandma|grandpa|eddy|flo|reed|rocko|sandy|shelley/i;

function score(v: SpeechSynthesisVoice): number {
  let s = 0;
  const lang = v.lang.replace("_", "-").toLowerCase();
  if (lang === "en-au") s += 30;
  else if (lang === "en-gb") s += 20;
  else if (lang === "en-us") s += 15;
  else if (lang.startsWith("en")) s += 5;
  if (/premium|enhanced|natural|neural|siri/i.test(v.name)) s += 40;
  if (/google/i.test(v.name)) s += 25;
  if (/karen|lee|catherine|daniel|serena|samantha/i.test(v.name)) s += 10;
  if (NOVELTY.test(v.name)) s -= 100;
  return s;
}

function bestVoice(): SpeechSynthesisVoice | undefined {
  try {
    const voices = window.speechSynthesis.getVoices().filter((v) => /^en/i.test(v.lang));
    return voices.sort((a, b) => score(b) - score(a))[0];
  } catch {
    return undefined;
  }
}

function browserSay(text: string, mine: number): Promise<void> {
  return new Promise((resolve) => {
    try {
      const synth = window.speechSynthesis;
      if (!synth || mine !== turn) return resolve();
      synth.cancel();
      const u = new SpeechSynthesisUtterance(text);
      const v = bestVoice();
      if (v) u.voice = v;
      u.lang = v?.lang ?? "en-AU";
      u.rate = 1.08;
      u.onend = u.onerror = () => resolve();
      synth.speak(u);
    } catch {
      resolve(); // no voice at all: the words are on screen
    }
  });
}
