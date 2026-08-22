import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

TOKEN = os.environ.get("BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"

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
                    "Boshqa xabarlar — takrorlanadi (echo)"
                )
            elif text.startswith("/help"):
                reply = (
                    "/start — boshlash\n"
                    "/info — bot haqida ma'lumot\n"
                    "O'zingiz yozgan har qanday matn takrorlanadi."
                )
            elif text.startswith("/info"):
                reply = "SirojAIorg_bot — python'da yozilgan oddiy Telegram bot."
            else:
                reply = f"{name}, siz yozdingiz: {text}"
            send_msg(chat_id, reply)


if __name__ == "__main__":
    main()
