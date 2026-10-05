/**
 * WhatsApp bridge — connects to your real WhatsApp account via
 * whatsapp-web.js (no Docker, no database, no Redis) and forwards
 * incoming messages to Jarvis's webhook, plus exposes a small REST API
 * for Jarvis to send messages back.
 *
 * The sending logic (and the fix for WhatsApp's "No LID for user" error)
 * lives in sender.js — read the header comment there.
 */

"use strict";

const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const axios = require("axios");
const crypto = require("crypto");
const { BridgeError, sendWithFallback, toBridgeError } = require("./sender");

const JARVIS_WEBHOOK_URL = process.env.JARVIS_WEBHOOK_URL || "http://localhost:8000/webhook";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET;
const BRIDGE_PORT = process.env.BRIDGE_PORT || 3001;
// Optional. Unset = listen on all interfaces (the previous behaviour, needed if Jarvis runs in Docker).
// If everything runs on this one machine, set BRIDGE_HOST=127.0.0.1 so other devices on your network
// can't reach the (unauthenticated) send endpoints.
const BRIDGE_HOST = process.env.BRIDGE_HOST;
const MAX_MEDIA_BYTES = (Number(process.env.MAX_MEDIA_MB) || 25) * 1024 * 1024;

if (!WEBHOOK_SECRET) {
  console.error("WEBHOOK_SECRET is not set — refusing to start. Set it to the same value as WEBHOOK_SECRET in Jarvis's .env.");
  process.exit(1);
}

// --- Never let a stray rejection from Puppeteer / WhatsApp Web kill the bridge -------------------
// (Node >= 15 exits on unhandled rejections by default; WhatsApp Web's own internal errors, such as
// "No LID for user", can surface this way.) Failed sends are still reported to Jarvis via HTTP.
process.on("unhandledRejection", (reason) => {
  const msg = String((reason && reason.message) || reason).split("\n")[0];
  console.error(`[bridge] unhandled rejection (still running): ${msg}`);
});
process.on("uncaughtException", (err) => {
  console.error(`[bridge] uncaught exception (still running): ${String(err && err.message).split("\n")[0]}`);
});

const client = new Client({ authStrategy: new LocalAuth() });
let isReady = false;

client.on("qr", (qr) => {
  console.log("\nScan this QR code with WhatsApp (Settings > Linked Devices > Link a Device):\n");
  qrcode.generate(qr, { small: true });
});

client.on("loading_screen", (percent, message) => {
  console.log(`Loading WhatsApp Web… ${percent}% ${message || ""}`.trim());
});

client.on("ready", () => {
  isReady = true;
  console.log("WhatsApp bridge is connected and ready.");
});

client.on("auth_failure", (msg) => {
  isReady = false;
  console.error("Authentication failed:", msg);
});

client.on("disconnected", (reason) => {
  isReady = false;
  console.error("WhatsApp disconnected:", reason, "— restart the bridge (npm start).");
});

// ---------------------------------------------------------------------------------------------
// Incoming messages  ->  Jarvis
// ---------------------------------------------------------------------------------------------

// Only 1:1 chats are answered. Group chats, status updates, channels and broadcast lists also
// arrive through the "message" event; replying to them would spam groups (as *you*) or try to
// post a status, so they are dropped here.
const PRIVATE_CHAT = /@(c\.us|lid)$/;
const MEDIA_KINDS = { ptt: "audio", audio: "audio", image: "image", document: "document" };

async function attachMedia(msg, payload) {
  try {
    const media = await msg.downloadMedia();
    if (!media || !media.data) {
      payload.media_error = "download_failed"; // expired / deleted / not available
      return;
    }
    if (Math.floor((media.data.length * 3) / 4) > MAX_MEDIA_BYTES) {
      payload.media_error = "too_large";
      return;
    }
    payload.media_base64 = media.data;
    payload.mimetype = media.mimetype;
    payload.filename = media.filename || `whatsapp_${payload.type}`;
  } catch (err) {
    console.error(`[in] could not download media: ${String(err.message).split("\n")[0]}`);
    payload.media_error = "download_failed";
  }
}

async function forwardToJarvis(payload) {
  const body = JSON.stringify(payload);
  const signature = "sha256=" + crypto.createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
  await axios.post(JARVIS_WEBHOOK_URL, body, {
    headers: { "Content-Type": "application/json", "x-webhook-signature": signature },
    timeout: 30000, // Jarvis acknowledges immediately and does the real work in the background
    maxBodyLength: Infinity,
    maxContentLength: Infinity,
  });
}

const recentIds = new Set();
function alreadyHandled(msg) {
  const id = msg.id && msg.id._serialized;
  if (!id) return false;
  if (recentIds.has(id)) return true;
  recentIds.add(id);
  if (recentIds.size > 1000) recentIds.delete(recentIds.values().next().value);
  return false;
}

async function handleIncoming(msg) {
  try {
    if (msg.fromMe) return;
    if (msg.isStatus || !PRIVATE_CHAT.test(msg.from || "")) return;
    if (alreadyHandled(msg)) return;

    // msg.from is the chat id exactly as WhatsApp gives it: "<digits>@c.us" or "<digits>@lid".
    // Jarvis replies to this same id (see sender.js for how it is made to work for both).
    let payload;
    const mediaKind = MEDIA_KINDS[msg.type];
    if (mediaKind) {
      payload = { sender: msg.from, from_me: false, type: mediaKind, text: msg.body || "" };
      if (msg.hasMedia) await attachMedia(msg, payload);
    } else if (msg.type === "chat" && (msg.body || "").trim()) {
      payload = { sender: msg.from, from_me: false, type: "text", text: msg.body };
    } else {
      return; // stickers, videos, locations, reactions, system notices… nothing Jarvis can act on
    }

    console.log(`[in] ${payload.type} from ${msg.from}`);
    await forwardToJarvis(payload);
  } catch (err) {
    const reason = err.code === "ECONNREFUSED" ? `Jarvis isn't running at ${JARVIS_WEBHOOK_URL}` : String(err.message).split("\n")[0];
    console.error(`[in] could not hand message to Jarvis: ${reason}`);
  }
}

client.on("message", handleIncoming);

// ---------------------------------------------------------------------------------------------
// REST API for Jarvis to call when sending messages back
// ---------------------------------------------------------------------------------------------

const app = express();
app.use(express.json({ limit: "50mb" }));

function requireReady(req, res, next) {
  if (!isReady) {
    return res.status(503).json({
      error: "WhatsApp isn't connected yet — wait for 'WhatsApp bridge is connected and ready.' (scan the QR code on first run).",
      code: "not_ready",
    });
  }
  next();
}

async function respond(res, label, job) {
  try {
    const sent = await job();
    res.json({ status: "sent", to: sent.to, via: sent.via });
  } catch (err) {
    const e = err instanceof BridgeError ? err : toBridgeError(err);
    console.error(`[out] ${label} failed (${e.status} ${e.code}): ${e.message}`);
    res.status(e.status).json({ error: e.message, code: e.code });
  }
}

app.get("/health", (req, res) => res.json({ ready: isReady }));

app.post("/send-text", requireReady, (req, res) => {
  const { to, text } = req.body || {};
  if (typeof text !== "string" || !text.trim()) {
    return res.status(400).json({ error: "'text' must be a non-empty string", code: "bad_request" });
  }
  return respond(res, "send-text", () => sendWithFallback(client, to, text, {}, console));
});

app.post("/send-audio", requireReady, (req, res) => {
  const { to, audio_base64, mimetype } = req.body || {};
  if (typeof audio_base64 !== "string" || !audio_base64) {
    return res.status(400).json({ error: "'audio_base64' must be a non-empty base64 string", code: "bad_request" });
  }
  const media = new MessageMedia(mimetype || "audio/ogg", audio_base64);
  return respond(res, "send-audio", () => sendWithFallback(client, to, media, { sendAudioAsVoice: true }, console));
});

// Close Chromium properly on Ctrl+C. Otherwise it can stay running in the background and the next
// `npm start` fails with "The browser is already running for .wwebjs_auth".
async function shutdown(signal) {
  console.log(`\n${signal} received — closing WhatsApp session…`);
  try {
    await client.destroy();
  } catch (_) {
    /* already closed */
  }
  process.exit(0);
}

function start() {
  client.initialize().catch((err) => {
    console.error(`[bridge] WhatsApp failed to start: ${String(err.message).split("\n")[0]}`);
    console.error("[bridge] If it says the browser is already running, close leftover Chrome/Chromium processes and retry.");
  });
  process.once("SIGINT", () => shutdown("SIGINT"));
  process.once("SIGTERM", () => shutdown("SIGTERM"));
  const onListening = () => console.log(`Bridge REST API listening on port ${BRIDGE_PORT}${BRIDGE_HOST ? ` (${BRIDGE_HOST})` : ""}`);
  return BRIDGE_HOST ? app.listen(BRIDGE_PORT, BRIDGE_HOST, onListening) : app.listen(BRIDGE_PORT, onListening);
}

if (require.main === module) start();

module.exports = { app, client, start, handleIncoming, setReady: (v) => (isReady = v) };