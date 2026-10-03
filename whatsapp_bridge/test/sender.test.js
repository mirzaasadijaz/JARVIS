"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { FakeWhatsApp } = require("./fake-whatsapp");
const { sendWithFallback, normalizeTarget, BridgeError } = require("../sender");

const quiet = { info() {}, warn() {} };
const LID = "22952607240241@lid"; // the kind of id your own DB shows (LID-only contact)
const send = (wa, to, content = "hi", opts = {}) => sendWithFallback(wa, to, content, opts, quiet);

// ---------------------------------------------------------------------------------------------
test("BASELINE: the original call pattern really does fail with your error", async () => {
  // Original server.js did: client.sendMessage(chatId, text)   (implicit sendSeen on)
  const wa = new FakeWhatsApp({ chats: [LID], sendSeenBroken: true });
  await assert.rejects(() => wa.sendMessage(LID, "hi"), /No LID for user/);
  assert.equal(wa.sent.length, 0);
});

test("BASELINE: a '@c.us' id built from LID digits (the old contact.number bug) fails too", async () => {
  const wa = new FakeWhatsApp({ chats: [LID] });
  await assert.rejects(() => wa.sendMessage("22952607240241@c.us", "hi"), /No LID for user/);
});

// ---------------------------------------------------------------------------------------------
test("reply to an existing LID chat survives a broken implicit sendSeen", async () => {
  const wa = new FakeWhatsApp({ chats: [LID], sendSeenBroken: true });
  const r = await send(wa, LID, "hello");
  assert.equal(r.via, "direct");
  assert.equal(wa.sent.length, 1);
  assert.equal(wa.sent[0].options.sendSeen, false);
});

test("unknown '@c.us' id (no mapping loaded): lookup establishes it, retry delivers exactly once", async () => {
  const wa = new FakeWhatsApp({ registered: { 923001234567: "5551234@lid" } });
  const r = await send(wa, "923001234567@c.us");
  assert.equal(r.via, "retry-after-lookup");
  assert.equal(wa.sent.length, 1, "must not be delivered twice");
  assert.deepEqual(
    wa.calls.map((c) => c.fn),
    ["sendMessage", "getContactLidAndPhone", "sendMessage"]
  );
});

test("falls through to the LID the lookup revealed when retrying the phone id still fails", async () => {
  const wa = new FakeWhatsApp({ registered: { 923001234567: "5551234@lid" }, lookupPopulates: false });
  const r = await send(wa, "923001234567@c.us");
  assert.equal(r.via, "alternate-id");
  assert.equal(r.to, "5551234@lid");
  assert.equal(wa.sent.length, 1);
});

test("bare phone number: verified with getNumberId first, then sent once", async () => {
  const wa = new FakeWhatsApp({ registered: { 923001234567: "5551234@lid" } });
  const r = await send(wa, "923001234567");
  assert.equal(r.via, "direct");
  assert.equal(r.to, "923001234567@c.us");
  assert.equal(wa.calls[0].fn, "getNumberId");
  assert.equal(wa.sent.length, 1);
});

test("bare phone number that is not on WhatsApp -> 404 and nothing is sent", async () => {
  const wa = new FakeWhatsApp({});
  await assert.rejects(
    () => send(wa, "923009999999"),
    (e) => e instanceof BridgeError && e.status === 404 && e.code === "not_on_whatsapp" && /international format/.test(e.message)
  );
  assert.equal(wa.calls.filter((c) => c.fn === "sendMessage").length, 0);
});

test("a failing getNumberId does not block the send", async () => {
  const wa = new FakeWhatsApp({ chats: ["923001234567@c.us"] });
  wa.getNumberId = async () => {
    throw new Error("Evaluation failed: boom");
  };
  const r = await send(wa, "923001234567");
  assert.equal(r.to, "923001234567@c.us");
});

// ---------------------------------------------------------------------------------------------
test("a NON-LID error is reported at once and never retried (no double sends)", async () => {
  const wa = new FakeWhatsApp({ chats: [LID], sessionClosed: true });
  await assert.rejects(
    () => send(wa, LID),
    (e) => e instanceof BridgeError && e.status === 503 && e.code === "session_unavailable"
  );
  assert.equal(wa.calls.filter((c) => c.fn === "sendMessage").length, 1);
  assert.equal(wa.calls.filter((c) => c.fn === "getContactLidAndPhone").length, 0);
});

test("when nothing works the error is a clean 502 that lists every attempt", async () => {
  const wa = new FakeWhatsApp({}); // unknown, unregistered "@c.us" id
  await assert.rejects(
    () => send(wa, "22952607240241@c.us"),
    (e) => e instanceof BridgeError && e.status === 502 && e.code === "no_lid" && /direct 22952607240241@c\.us/.test(e.message) && /retry-after-lookup/.test(e.message)
  );
  assert.equal(wa.sent.length, 0);
});

test("a throwing lookup is survived (it is best-effort)", async () => {
  const wa = new FakeWhatsApp({ lookupThrows: true });
  await assert.rejects(() => send(wa, "923001234567@c.us"), (e) => e instanceof BridgeError && e.status === 502);
});

test("sendMessage resolving undefined (chat could not be opened) is treated as a failure, not 'sent'", async () => {
  const wa = new FakeWhatsApp({});
  await assert.rejects(() => send(wa, "120363000000@g.us"), (e) => e instanceof BridgeError && e.status === 502);
  assert.equal(wa.calls.filter((c) => c.fn === "getContactLidAndPhone").length, 0, "no LID logic for groups");
});

test("group ids are passed through untouched", async () => {
  const wa = new FakeWhatsApp({ chats: ["120363000000@g.us"] });
  const r = await send(wa, "120363000000@g.us");
  assert.equal(r.to, "120363000000@g.us");
});

test("media + options are forwarded, sendSeen is always forced off", async () => {
  const wa = new FakeWhatsApp({ chats: [LID] });
  const media = { mimetype: "audio/mpeg", data: "AAAA" };
  await send(wa, LID, media, { sendAudioAsVoice: true, sendSeen: true });
  assert.equal(wa.sent[0].content, media);
  assert.equal(wa.sent[0].options.sendAudioAsVoice, true);
  assert.equal(wa.sent[0].options.sendSeen, false);
});

// ---------------------------------------------------------------------------------------------
test("normalizeTarget", () => {
  assert.deepEqual(normalizeTarget("923001234567").id, "923001234567@c.us");
  assert.equal(normalizeTarget("923001234567").bare, true);
  assert.equal(normalizeTarget("+92 300 1234567").id, "923001234567@c.us");
  assert.equal(normalizeTarget(923001234567).id, "923001234567@c.us");
  assert.equal(normalizeTarget("923001234567@c.us").bare, false);
  assert.equal(normalizeTarget(LID).kind, "lid");
  assert.equal(normalizeTarget("1203630@g.us").kind, "passthrough");
  assert.equal(normalizeTarget("status@broadcast").kind, "passthrough");
  for (const bad of [undefined, null, "", "   ", "abc", "123", "@c.us", {}, "1".repeat(20)]) {
    assert.throws(() => normalizeTarget(bad), (e) => e instanceof BridgeError && e.status === 400, `should reject ${JSON.stringify(bad)}`);
  }
});
