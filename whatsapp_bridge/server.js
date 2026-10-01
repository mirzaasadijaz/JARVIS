/**
 * WhatsApp bridge — connects to your real WhatsApp account via
 * whatsapp-web.js (no Docker, no database, no Redis) and forwards
 * incoming messages to Jarvis's webhook, plus exposes a small REST API
 * for Jarvis to send messages back.
 */

const { Client, LocalAuth, MessageMedia } = require("whatsapp-web.js");
const qrcode = require("qrcode-terminal");
const express = require("express");
const axios = require("axios");
const crypto = require("crypto");

const JARVIS_WEBHOOK_URL = process.env.JARVIS_WEBHOOK_URL || "http://localhost:8000/webhook";
const WEBHOOK_SECRET = process.env.WEBHOOK_SECRET;
const BRIDGE_PORT = process.env.BRIDGE_PORT || 3001;

if (!WEBHOOK_SECRET) {
  console.error("WEBHOOK_SECRET is not set — refusing to start. Set it to the same value as WEBHOOK_SECRET in Jarvis's .env.");
  process.exit(1);
}

const client = new Client({ authStrategy: new LocalAuth() });

client.on("qr", (qr) => {
  console.log("\nScan this QR code with WhatsApp (Settings > Linked Devices > Link a Device):\n");
  qrcode.generate(qr, { small: true });
});

client.on("ready", () => {
  console.log("WhatsApp bridge is connected and ready.");
});

client.on("auth_failure", (msg) => {
  console.error("Authentication failed:", msg);
});

client.on("disconnected", (reason) => {
  console.error("WhatsApp disconnected:", reason);
});

function categorize(msgType) {
  if (msgType === "ptt" || msgType === "audio") return "audio";
  if (msgType === "image") return "image";
  if (msgType === "document") return "document";
  return "text";
}

client.on("message", async (msg) => {
  try {
    // FIX: Using msg.from instead of contact.number to guarantee a valid WhatsApp ID
    const payload = {
      sender: msg.from, 
      from_me: msg.fromMe,
      type: categorize(msg.type),
      text: msg.body || "",
    };

    if (msg.hasMedia) {
      const media = await msg.downloadMedia();
      payload.media_base64 = media.data;
      payload.mimetype = media.mimetype;
      payload.filename = media.filename || `whatsapp_${payload.type}`;
    }

    await forwardToJarvis(payload);
  } catch (err) {
    console.error("Error handling incoming message:", err.message);
  }
});

async function forwardToJarvis(payload) {
  const body = JSON.stringify(payload);
  const signature = "sha256=" + crypto.createHmac("sha256", WEBHOOK_SECRET).update(body).digest("hex");
  await axios.post(JARVIS_WEBHOOK_URL, body, {
    headers: { "Content-Type": "application/json", "x-webhook-signature": signature },
  });
}

client.initialize();

// --- REST API for Jarvis to call when sending messages back ---
const app = express();
app.use(express.json({ limit: "50mb" }));

app.post("/send-text", async (req, res) => {
  try {
    const { to, text } = req.body;
    // FIX: Only append @c.us if it doesn't already exist in the 'to' string
    const chatId = (to && to.includes('@')) ? to : `${to}@c.us`;
    await client.sendMessage(chatId, text);
    res.json({ status: "sent" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.post("/send-audio", async (req, res) => {
  try {
    const { to, audio_base64, mimetype } = req.body;
    // FIX: Only append @c.us if it doesn't already exist in the 'to' string
    const chatId = (to && to.includes('@')) ? to : `${to}@c.us`;
    const media = new MessageMedia(mimetype || "audio/ogg", audio_base64);
    await client.sendMessage(chatId, media, { sendAudioAsVoice: true });
    res.json({ status: "sent" });
  } catch (err) {
    res.status(500).json({ error: err.message });
  }
});

app.listen(BRIDGE_PORT, () => console.log(`Bridge REST API listening on port ${BRIDGE_PORT}`));