/**
 * A fake whatsapp-web.js Client that behaves like the real one does in the
 * LID era — modelled on the library source (Client.sendMessage ->
 * WWebJS.getChat -> findOrCreateLatestChat -> toUserLidOrThrow, and
 * WWebJS.sendSeen), so the "No LID for user" failure can be reproduced and
 * the fix verified without a phone, a QR code or a browser.
 */
"use strict";

const EventEmitter = require("node:events");

// The exact error text from the bug report (WhatsApp Web's own throw site).
const noLid = () =>
  new Error("No LID for user\ns (https://static.whatsapp.net/rsrc.php/v4/y0/r/1ypFDhyoVzg.js:85:180)");

class FakeWhatsApp {
  /**
   * chats            chat ids already present in WhatsApp Web's chat store
   * lidMap           { "<digits>@c.us": "<lid>@lid" }  mappings already loaded in the page
   * registered       { "<digits>": "<lid>@lid" }       numbers that exist on WhatsApp
   * sendSeenBroken   implicit mark-as-read throws No LID (library: WWebJS.sendSeen)
   * lookupPopulates  does getContactLidAndPhone load the mapping as a side effect (real lib: yes)
   * lookupThrows     getContactLidAndPhone itself blows up
   * sessionClosed    puppeteer page is gone
   */
  constructor(opts = {}) {
    this.chats = new Set(opts.chats || []);
    this.lidMap = new Map(Object.entries(opts.lidMap || {}));
    this.registered = new Map(Object.entries(opts.registered || {}));
    this.sendSeenBroken = !!opts.sendSeenBroken;
    this.lookupPopulates = opts.lookupPopulates !== false;
    this.lookupThrows = !!opts.lookupThrows;
    this.sessionClosed = !!opts.sessionClosed;
    this.sent = []; // successful deliveries
    this.calls = []; // every call, in order
  }

  async sendMessage(chatId, content, options = {}) {
    this.calls.push({ fn: "sendMessage", chatId, options });
    if (this.sessionClosed) {
      throw new Error("Protocol error (Runtime.callFunctionOn): Session closed. Most likely the page has been closed.");
    }

    // --- WWebJS.getChat: Chat.get(wid) || findOrCreateLatestChat(wid) ---
    if (!this.chats.has(chatId)) {
      if (chatId.endsWith("@c.us")) {
        if (!this.lidMap.has(chatId)) throw noLid(); // toUserLidOrThrow(pn) with no mapping
        this.chats.add(chatId);
      } else if (chatId.endsWith("@lid")) {
        this.chats.add(chatId); // a LID needs no conversion
      } else {
        return undefined; // library: `if (!chat) return null` -> sendMessage resolves undefined
      }
    }

    // --- WWebJS.sendSeen (runs unless options.sendSeen === false) ---
    if (options.sendSeen !== false && this.sendSeenBroken) throw noLid();

    this.sent.push({ chatId, content, options });
    return { id: { _serialized: `true_${chatId}_${this.sent.length}` } };
  }

  // Library: enforceLidAndPnRetrieval -> queryWidExists, which loads the mapping.
  async getContactLidAndPhone(id) {
    this.calls.push({ fn: "getContactLidAndPhone", id });
    if (this.lookupThrows) throw new Error("Evaluation failed: lookup exploded");
    if (id.endsWith("@c.us")) {
      const digits = id.split("@")[0];
      const lid = this.registered.get(digits);
      if (!lid) return [{ lid: undefined, pn: undefined }];
      if (this.lookupPopulates) this.lidMap.set(id, lid);
      return [{ lid, pn: id }];
    }
    // LID input: phone is only known for some contacts
    for (const [digits, lid] of this.registered) if (lid === id) return [{ lid, pn: `${digits}@c.us` }];
    return [{ lid: undefined, pn: undefined }];
  }

  // Library: getNumberId(number) -> queryWidExists; null when not on WhatsApp.
  async getNumberId(number) {
    this.calls.push({ fn: "getNumberId", number });
    const lid = this.registered.get(number);
    if (!lid) return null;
    if (this.lookupPopulates) this.lidMap.set(`${number}@c.us`, lid);
    return { server: "c.us", user: number, _serialized: `${number}@c.us` };
  }
}

/** Drop-in for require("whatsapp-web.js") used by server.test.js. */
function makeStubModule(fakeWhatsApp) {
  class Client extends EventEmitter {
    constructor() {
      super();
      this.wa = fakeWhatsApp;
    }
    initialize() {
      return Promise.resolve();
    }
    destroy() {
      return Promise.resolve();
    }
    sendMessage(...a) {
      return this.wa.sendMessage(...a);
    }
    getContactLidAndPhone(...a) {
      return this.wa.getContactLidAndPhone(...a);
    }
    getNumberId(...a) {
      return this.wa.getNumberId(...a);
    }
  }
  class LocalAuth {}
  class MessageMedia {
    constructor(mimetype, data) {
      this.mimetype = mimetype;
      this.data = data;
    }
  }
  return { Client, LocalAuth, MessageMedia };
}

module.exports = { FakeWhatsApp, makeStubModule, noLid };
