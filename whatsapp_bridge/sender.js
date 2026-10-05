/**
 * Sending logic for the bridge — deliberately free of Express/Puppeteer so it
 * can be unit-tested against a fake client (see test/sender.test.js).
 *
 * WHY THIS FILE EXISTS — the `No LID for user` error
 * --------------------------------------------------
 * WhatsApp is moving every account to "LID" addressing (an opaque id such as
 * `22952607240241@lid` instead of the phone number `<number>@c.us`).
 * whatsapp-web.js 1.34.x drives the real WhatsApp Web page, and that page
 * throws `No LID for user` from its own `toUserLidOrThrow()` whenever it is
 * asked to open/send to a 1:1 chat whose phone <-> LID mapping it has not
 * loaded yet. Two places in client.sendMessage() can trigger it:
 *
 *   1. WWebJS.getChat -> findOrCreateLatestChat   (chat not in the store yet:
 *      a stranger who just messaged you, a number you never chatted with, or
 *      a `...@c.us` id that is really a LID with the digits copied over)
 *   2. WWebJS.sendSeen                            (the implicit "mark as read")
 *
 * 1.34.7 is the newest published release, so there is no upgrade that fixes
 * it. What works is to (a) never trigger the fragile implicit sendSeen,
 * (b) ask the library to establish the mapping for unknown contacts
 * (client.getContactLidAndPhone — added in 1.34.0 for exactly this), and
 * (c) retry with every id the lookup gives us. Anything that is NOT a LID
 * problem (session closed, bad input, ...) is reported immediately and never
 * retried, so a message can't be sent twice.
 */

"use strict";

/** An error that already knows which HTTP status the REST API should use. */
class BridgeError extends Error {
  constructor(message, status = 500, code = "send_failed") {
    super(message);
    this.name = "BridgeError";
    this.status = status;
    this.code = code;
  }
}

/** sendMessage resolved but returned nothing => WhatsApp could not open the chat. */
class ChatNotOpenedError extends Error {
  constructor(id) {
    super(`WhatsApp could not open a chat with ${id}`);
    this.name = "ChatNotOpenedError";
  }
}

const LID_ERROR = /no lid for user/i;
const SESSION_GONE = /target closed|session closed|browser has disconnected|execution context was destroyed|detached frame|not connected/i;

const errText = (err) => String((err && err.message) || err || "");
const firstLine = (s) => errText(s).split("\n")[0].trim();

function isLidError(err) {
  return LID_ERROR.test(errText(err));
}

/** Failures worth retrying with a different id / after a mapping lookup. */
function isRecoverable(err) {
  return isLidError(err) || err instanceof ChatNotOpenedError;
}

/**
 * Turns whatever the caller passed as `to` into a chat id.
 *   "923001234567"          -> phone (bare)  923001234567@c.us
 *   "+92 300 1234567"       -> phone (bare)  923001234567@c.us
 *   "923001234567@c.us"     -> phone         923001234567@c.us
 *   "22952607240241@lid"    -> lid           22952607240241@lid
 *   "1203...@g.us" etc.     -> passthrough   (groups/channels: no LID logic)
 */
function normalizeTarget(to) {
  if (typeof to !== "string" && typeof to !== "number") {
    throw new BridgeError("'to' is required (phone number in international format, or a WhatsApp chat id)", 400, "bad_request");
  }
  const raw = String(to).trim();
  if (!raw) {
    throw new BridgeError("'to' is required (phone number in international format, or a WhatsApp chat id)", 400, "bad_request");
  }

  const at = raw.indexOf("@");
  const user = at === -1 ? raw : raw.slice(0, at);
  const server = at === -1 ? "c.us" : raw.slice(at + 1).toLowerCase();
  const digits = user.replace(/\D/g, "");

  if (server === "c.us") {
    if (digits.length < 7 || digits.length > 15) {
      throw new BridgeError(
        `'${raw}' is not a valid phone number — use international format without '+', e.g. 923001234567`,
        400,
        "bad_request"
      );
    }
    return { kind: "phone", bare: at === -1, digits, id: `${digits}@c.us` };
  }
  if (server === "lid") {
    if (!digits) throw new BridgeError(`'${raw}' is not a valid WhatsApp LID`, 400, "bad_request");
    return { kind: "lid", bare: false, digits, id: `${digits}@lid` };
  }
  return { kind: "passthrough", bare: false, digits, id: raw }; // @g.us, @newsletter, @broadcast, ...
}

/** Maps low-level failures onto an HTTP status + a message a human can act on. */
function toBridgeError(err) {
  if (err instanceof BridgeError) return err;
  const msg = firstLine(err) || "Unknown error";
  if (SESSION_GONE.test(errText(err))) {
    return new BridgeError(
      `The WhatsApp browser session is not available (${msg}). Restart the bridge (npm start).`,
      503,
      "session_unavailable"
    );
  }
  return new BridgeError(msg, 500, "send_failed");
}

/**
 * Asks WhatsApp to establish the phone <-> LID mapping for an unknown contact.
 * Never throws — it is a best-effort step; returns {} if nothing was learned.
 */
async function lookupMapping(client, id, log) {
  try {
    if (typeof client.getContactLidAndPhone !== "function") return {};
    const res = await client.getContactLidAndPhone(id);
    const first = Array.isArray(res) ? res[0] : res;
    return { lid: first && first.lid, pn: first && first.pn };
  } catch (err) {
    log.warn(`[send] LID lookup for ${id} failed: ${firstLine(err)}`);
    return {};
  }
}

/**
 * For a bare phone number (typed by a person / chosen by the LLM) confirm it is
 * actually on WhatsApp. Without this, WhatsApp happily "sends" to nobody and the
 * message sits on a clock icon forever. This lookup also loads the LID mapping,
 * which prevents the error in the first place.
 * Returns the id to use first.
 */
async function verifyRegistered(client, target, log) {
  let wid;
  try {
    wid = await client.getNumberId(target.digits);
  } catch (err) {
    // Couldn't ask — don't block the send, just try the obvious id.
    log.warn(`[send] getNumberId(${target.digits}) failed: ${firstLine(err)}`);
    return target.id;
  }
  if (!wid) {
    throw new BridgeError(
      `${target.digits} is not registered on WhatsApp. Check the number — international format, no '+' and no leading zero (e.g. 923001234567).`,
      404,
      "not_on_whatsapp"
    );
  }
  return wid._serialized || target.id;
}

const config = { graceMs: 500, attemptTimeoutMs: 60000 };
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// One send at a time, so "was MY message created?" below can't be confused with another send.
let queue = Promise.resolve();
function serialized(job) {
  const run = queue.then(job);
  queue = run.catch(() => {});
  return run;
}

// WhatsApp emits "message_create" as soon as a message is queued, even if sendMessage() then fails.
function watchDispatch(client, content) {
  if (typeof client.on !== "function" || typeof client.removeListener !== "function") {
    return { supported: false, created: () => null, stop() {} };
  }
  const isText = typeof content === "string";
  const wanted = isText ? content.trim() : null;
  let created = null;
  const onCreate = (msg) => {
    if (created || !msg || !msg.fromMe) return;
    if (isText ? String(msg.body || "").trim() === wanted : msg.hasMedia) created = msg;
  };
  client.on("message_create", onCreate);
  return { supported: true, created: () => created, stop: () => client.removeListener("message_create", onCreate) };
}

// Runs INSIDE the WhatsApp Web page: is a matching message we sent already in its message store?
function pageHasOutgoing(body, isMedia, since) {
  const { Msg, Chat } = window.require("WAWebCollections");
  let list = typeof Msg.getModelsArray === "function" ? Msg.getModelsArray() : null;
  if (!list) {
    list = [];
    for (const chat of Chat.getModelsArray()) {
      if (chat.msgs && typeof chat.msgs.getModelsArray === "function") list.push(...chat.msgs.getModelsArray());
    }
  }
  return list.some(
    (m) =>
      m &&
      m.id &&
      m.id.fromMe &&
      m.t >= since &&
      (isMedia ? m.type === "ptt" || m.type === "audio" : typeof m.body === "string" && m.body.trim() === body)
  );
}

async function storeHasOutgoing(client, content, since, log) {
  if (!client.pupPage || typeof client.pupPage.evaluate !== "function") return false;
  try {
    const isMedia = typeof content !== "string";
    return Boolean(await client.pupPage.evaluate(pageHasOutgoing, isMedia ? "" : content.trim(), isMedia, since));
  } catch (err) {
    log.warn(`[send] could not inspect WhatsApp's message store: ${firstLine(err)}`);
    return false;
  }
}

// Did a failed attempt actually send the message? Either signal is enough; resending after it = duplicates.
async function wasDispatched(client, watch, content, since, log) {
  if (watch.created()) return true;
  if (await storeHasOutgoing(client, content, since, log)) return true;
  if (!watch.supported) return false;
  await sleep(config.graceMs);
  return Boolean(watch.created());
}

function withTimeout(promise, ms, id) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(
      () => reject(new BridgeError(`WhatsApp did not answer within ${Math.round(ms / 1000)}s while sending to ${id}.`, 504, "send_timeout")),
      ms
    );
  });
  return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
}

function sendWithFallback(client, to, content, options = {}, log = console) {
  return serialized(() => send(client, to, content, options, log));
}

async function send(client, to, content, options, log) {
  const target = normalizeTarget(to);
  const sendOptions = { ...options, sendSeen: false };
  const firstId = target.kind === "phone" && target.bare ? await verifyRegistered(client, target, log) : target.id;

  const failures = [];
  const delivered = (id, via, message) => {
    if (via !== "direct") log.info(`[send] delivered via ${via} (${id})`);
    return { to: id, via, messageId: message && message.id && message.id._serialized };
  };

  const attempt = async (id, via) => {
    const watch = watchDispatch(client, content);
    const since = Math.floor(Date.now() / 1000);
    try {
      const sent = await withTimeout(client.sendMessage(id, content, sendOptions), config.attemptTimeoutMs, id);
      if (sent) return delivered(id, via, sent);
      // Resolved with nothing: either the chat couldn't be opened, or it was sent but not found again.
      if (await wasDispatched(client, watch, content, since, log)) return delivered(id, `${via}, library returned no message`, watch.created());
      failures.push(`${via} ${id}: ${new ChatNotOpenedError(id).message}`);
      return null;
    } catch (err) {
      // It threw. If the message was already created it IS on its way, so never resend it.
      if (await wasDispatched(client, watch, content, since, log)) {
        log.warn(`[send] WhatsApp reported "${firstLine(err)}" AFTER the message was sent; not retrying`);
        return delivered(id, `${via}, error after send ignored`, watch.created());
      }
      if (!isRecoverable(err)) throw toBridgeError(err);
      failures.push(`${via} ${id}: ${firstLine(err)}`);
      return null;
    } finally {
      watch.stop();
    }
  };

  let done = await attempt(firstId, "direct");
  if (done) return done;

  if (target.kind !== "passthrough") {
    const mapping = await lookupMapping(client, firstId, log);
    const candidates = [...new Set([firstId, mapping.lid, mapping.pn].filter(Boolean))];
    for (const id of candidates) {
      done = await attempt(id, id === firstId ? "retry-after-lookup" : "alternate-id");
      if (done) return done;
    }
  }

  throw new BridgeError(
    `WhatsApp refused to open the chat ("No LID for user"). Tried: ${failures.join(" | ")}. ` +
      `The contact may not have messaged this account yet — ask them to send a message first, ` +
      `or restart the bridge so WhatsApp Web reloads its contact mapping.`,
    502,
    "no_lid"
  );
}

module.exports = {
  BridgeError,
  ChatNotOpenedError,
  isLidError,
  normalizeTarget,
  toBridgeError,
  sendWithFallback,
};