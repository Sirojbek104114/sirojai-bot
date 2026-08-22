import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

TOKEN = os.environ.get("BOT_TOKEN", "")
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-lite-latest")
API = f"https://api.telegram.org/bot{TOKEN}"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("bot")


def call(method, **params):
    try:
        r = requests.post(f"{API}/{method}", data=params, timeout=60)
        return r.json()
    except Exception as e:
        log.error("API error: %s", e)
        return None


def get_updates(offset):
    return call("getUpdates", timeout=30, offset=offset, allowed_updates='["message"]')


def send_msg(chat_id, text):
    call("sendMessage", chat_id=chat_id, text=text)


def send_typing(chat_id):
    call("sendChatAction", chat_id=chat_id, action="typing")


def ask_gemini(prompt, history=None):
    contents = []
    for h in (history or [])[-8:]:
        contents.append({"role": h["role"], "parts": [{"text": h["text"]}]})
    contents.append({"role": "user", "parts": [{"text": prompt}]})
    try:
        r = requests.post(
            f"{GEMINI_URL}?key={GEMINI_KEY}",
            json={"contents": contents},
            timeout=60,
        )
        data = r.json()
        if "candidates" in data and data["candidates"]:
            parts = data["candidates"][0]["content"]["parts"]
            return "".join(p.get("text", "") for p in parts).strip()
        log.error("Gemini no candidates. status=%s body=%s", r.status_code, str(data)[:300])
        err = data.get("error", {})
        detail = err.get("message", str(data)[:200]) if isinstance(err, dict) else str(data)[:200]
        return f"AI xato (status {r.status_code}): {detail}"
    except Exception as e:
        log.error("Gemini error: %s", e)
        return "AI bilan bog'lanishda xatolik yuz berdi."


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass


def start_health_server():
    server = HTTPServer(("0.0.0.0", 8080), HealthHandler)
    log.info("Health server on :8080")
    server.serve_forever()


def main():
    if not TOKEN:
        log.error("BOT_TOKEN env variable not set")
        return
    threading.Thread(target=start_health_server, daemon=True).start()
    log.info("Bot started")
    offset = 0
    chat_history = {}
    while True:
        data = get_updates(offset)
        if not data or not data.get("ok"):
            time.sleep(3)
            continue
        for upd in data["result"]:
            offset = upd["update_id"] + 1
            msg = upd.get("message")
            if not msg or "text" not in msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg["text"]
            user = msg["from"]
            name = user.get("first_name", "Do'stim")
            log.info("From %s: %s", name, text)
            if text.startswith("/start"):
                reply = (
                    f"Salom, {name}! Men SirojAIorg_botman.\n\n"
                    "Buyruqlar:\n"
                    "/help — yordam\n"
                    "/info — bot haqida\n"
                    "/clear — suhbat tarixini tozalash\n"
                    "Boshqa xabarlar — AI (Gemini) javob beradi"
                )
            elif text.startswith("/help"):
                reply = (
                    "/start — boshlash\n"
                    "/info — bot haqida ma'lumot\n"
                    "/status — bot holati\n"
                    "/clear — suhbat tarixini tozalash\n"
                    "Har qanday matn yozing — AI javob beradi."
                )
            elif text.startswith("/clear"):
                chat_history[chat_id] = []
                reply = "Suhbat tarixi tozalandi. Yangi savol bering!"
            elif text.startswith("/info"):
                reply = (
                    "SirojAIorg_bot — Gemini AI bilan ishlaydigan Telegram bot.\n"
                    f"Model: {GEMINI_MODEL}"
                )
            elif text.startswith("/status"):
                reply = (
                    f"Bot: ishlayapti\n"
                    f"Model: {GEMINI_MODEL}\n"
                    f"GEMINI_API_KEY: {'bor' if GEMINI_KEY else 'YOQ — sozlanmagan'}"
                )
            else:
                send_typing(chat_id)
                reply = ask_gemini(text, chat_history.get(chat_id, []))
                chat_history.setdefault(chat_id, []).extend(
                    [
                        {"role": "user", "text": text},
                        {"role": "model", "text": reply},
                    ]
                )
            send_msg(chat_id, reply)


if __name__ == "__main__":
    main()
