"use strict";

/**
 * End-to-end test of the real server.js: the real Express app, the real
 * message handler, the real HMAC signing — only the WhatsApp library is
 * replaced by test/fake-whatsapp.js, and "Jarvis" is a tiny local HTTP server.
 */

const test = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");
const crypto = require("node:crypto");
const Module = require("node:module");
const { FakeWhatsApp, makeStubModule } = require("./fake-whatsapp");

const SECRET = "test-secret";
const LID = "22952607240241@lid";

let jarvis, jarvisPort, received, jarvisMode;
let bridge, base, wa;

function startFakeJarvis() {
  received = [];
  jarvisMode = "ok";
  return new Promise((resolve) => {
    jarvis = http.createServer((req, res) => {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        received.push({ raw, headers: req.headers, json: JSON.parse(raw) });
        res.statusCode = jarvisMode === "ok" ? 200 : 500;
        res.setHeader("content-type", "application/json");
        res.end(JSON.stringify({ status: "ok" }));
      });
    });
    jarvis.listen(0, "127.0.0.1", () => resolve(jarvis.address().port));
  });
}

test.before(async () => {
  jarvisPort = await startFakeJarvis();
  process.env.WEBHOOK_SECRET = SECRET;
  process.env.JARVIS_WEBHOOK_URL = `http://127.0.0.1:${jarvisPort}/webhook`;
  process.env.BRIDGE_PORT = "0";
  process.env.BRIDGE_HOST = "127.0.0.1";
  process.env.MAX_MEDIA_MB = "1";

  wa = new FakeWhatsApp({ chats: [LID], registered: { 923001234567: "5551234@lid" } });
  const stub = makeStubModule(wa);
  const origLoad = Module._load;
  Module._load = function (request, ...rest) {
    return request === "whatsapp-web.js" ? stub : origLoad.call(this, request, ...rest);
  };

  const server = require("../server");
  bridge = server;
  const httpServer = server.start();
  await new Promise((r) => httpServer.once("listening", r));
  base = `http://127.0.0.1:${httpServer.address().port}`;
  bridge._httpServer = httpServer;
});

test.after(async () => {
  bridge._httpServer.closeAllConnections?.();
  await new Promise((r) => bridge._httpServer.close(r));
  await new Promise((r) => jarvis.close(r));
  process.removeAllListeners("SIGINT");
  process.removeAllListeners("SIGTERM");
});

const post = (path, body) =>
  fetch(base + path, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) }).then(async (r) => ({
    status: r.status,
    body: await r.json(),
  }));

const fakeMsg = (over = {}) => ({ fromMe: false, isStatus: false, from: LID, type: "chat", body: "hello jarvis", hasMedia: false, ...over });

// ---------------------------------------------------------------------------------------------
test("sending before WhatsApp is ready -> 503 not_ready (not a cryptic 500)", async () => {
  bridge.setReady(false);
  const r = await post("/send-text", { to: LID, text: "hi" });
  assert.equal(r.status, 503);
  assert.equal(r.body.code, "not_ready");
  assert.equal((await (await fetch(base + "/health")).json()).ready, false);
});

test("once 'ready' fires the bridge reports healthy", async () => {
  bridge.client.emit("ready");
  assert.equal((await (await fetch(base + "/health")).json()).ready, true);
});

test("POST /send-text to a LID chat with a broken sendSeen succeeds ({status:'sent'})", async () => {
  wa.sendSeenBroken = true;
  const r = await post("/send-text", { to: LID, text: "hi from jarvis" });
  assert.equal(r.status, 200);
  assert.equal(r.body.status, "sent");
  assert.equal(wa.sent.at(-1).content, "hi from jarvis");
  wa.sendSeenBroken = false;
});

test("POST /send-text validates input -> 400", async () => {
  for (const body of [{ to: LID }, { to: LID, text: "   " }, { to: LID, text: 5 }, { text: "x" }, { to: "abc", text: "x" }]) {
    const r = await post("/send-text", body);
    assert.equal(r.status, 400, JSON.stringify(body));
    assert.ok(r.body.error);
  }
});

test("POST /send-text to an unregistered number -> 404 with an actionable message", async () => {
  const r = await post("/send-text", { to: "923009999999", text: "hi" });
  assert.equal(r.status, 404);
  assert.equal(r.body.code, "not_on_whatsapp");
});

test("POST /send-text to a number we never chatted with works (LID mapping is established)", async () => {
  const r = await post("/send-text", { to: "923001234567", text: "first contact" });
  assert.equal(r.status, 200);
  assert.equal(wa.sent.at(-1).chatId, "923001234567@c.us");
});

test("POST /send-audio sends a voice note and validates input", async () => {
  const ok = await post("/send-audio", { to: LID, audio_base64: "AAAA", mimetype: "audio/mpeg" });
  assert.equal(ok.status, 200);
  assert.equal(wa.sent.at(-1).options.sendAudioAsVoice, true);
  assert.equal(wa.sent.at(-1).content.mimetype, "audio/mpeg");
  assert.equal((await post("/send-audio", { to: LID })).status, 400);
});

test("a dead browser session is a 503, not a crash", async () => {
  wa.sessionClosed = true;
  const r = await post("/send-text", { to: LID, text: "hi" });
  assert.equal(r.status, 503);
  assert.equal(r.body.code, "session_unavailable");
  wa.sessionClosed = false;
});

// ---------------------------------------------------------------------------------------------
test("incoming 1:1 text is forwarded with a valid HMAC signature", async () => {
  received.length = 0;
  await bridge.handleIncoming(fakeMsg());
  assert.equal(received.length, 1);
  const { raw, headers, json } = received[0];
  const expected = "sha256=" + crypto.createHmac("sha256", SECRET).update(raw).digest("hex");
  assert.equal(headers["x-webhook-signature"], expected);
  assert.deepEqual(json, { sender: LID, from_me: false, type: "text", text: "hello jarvis" });
});

test("both address formats are forwarded as-is", async () => {
  received.length = 0;
  await bridge.handleIncoming(fakeMsg({ from: "923001234567@c.us" }));
  assert.equal(received[0].json.sender, "923001234567@c.us");
});

test("things Jarvis must NOT answer are dropped: groups, statuses, own msgs, stickers, empty, reactions", async () => {
  received.length = 0;
  await bridge.handleIncoming(fakeMsg({ from: "120363000000@g.us" }));
  await bridge.handleIncoming(fakeMsg({ from: "status@broadcast", isStatus: true }));
  await bridge.handleIncoming(fakeMsg({ isStatus: true }));
  await bridge.handleIncoming(fakeMsg({ fromMe: true }));
  await bridge.handleIncoming(fakeMsg({ type: "sticker", body: "" }));
  await bridge.handleIncoming(fakeMsg({ type: "location", body: "/9j/4AAQSkZJRg-base64-thumbnail" }));
  await bridge.handleIncoming(fakeMsg({ type: "reaction", body: "👍" }));
  await bridge.handleIncoming(fakeMsg({ body: "   " }));
  await bridge.handleIncoming(fakeMsg({ from: "1203@newsletter" }));
  assert.equal(received.length, 0);
});

test("voice note: media is downloaded and forwarded as audio", async () => {
  received.length = 0;
  const media = { data: Buffer.from("opus-bytes").toString("base64"), mimetype: "audio/ogg; codecs=opus" };
  await bridge.handleIncoming(fakeMsg({ type: "ptt", body: "", hasMedia: true, downloadMedia: async () => media }));
  assert.equal(received[0].json.type, "audio");
  assert.equal(received[0].json.media_base64, media.data);
  assert.equal(received[0].json.mimetype, media.mimetype);
});

test("media that can't be downloaded is still forwarded, flagged, instead of vanishing", async () => {
  received.length = 0;
  await bridge.handleIncoming(fakeMsg({ type: "image", body: "", hasMedia: true, downloadMedia: async () => undefined }));
  await bridge.handleIncoming(fakeMsg({ type: "document", body: "", hasMedia: true, downloadMedia: async () => { throw new Error("boom"); } }));
  assert.equal(received.length, 2);
  for (const r of received) {
    assert.equal(r.json.media_error, "download_failed");
    assert.equal(r.json.media_base64, undefined);
  }
});

test("oversized media is flagged rather than shipped", async () => {
  received.length = 0;
  const big = { data: "A".repeat(2 * 1024 * 1024), mimetype: "application/pdf" }; // ~1.5 MB > MAX_MEDIA_MB=1
  await bridge.handleIncoming(fakeMsg({ type: "document", body: "", hasMedia: true, downloadMedia: async () => big }));
  assert.equal(received[0].json.media_error, "too_large");
  assert.equal(received[0].json.media_base64, undefined);
});

test("Jarvis being down or erroring never throws out of the handler", async () => {
  jarvisMode = "error";
  await assert.doesNotReject(() => bridge.handleIncoming(fakeMsg()));
  jarvisMode = "ok";
});
