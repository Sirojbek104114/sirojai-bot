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


def send_document(chat_id, filename, content, caption=""):
    try:
        files = {"document": (filename, content, "text/html")}
        requests.post(
            f"{API}/sendDocument",
            data={"chat_id": chat_id, "caption": caption},
            files=files,
            timeout=60,
        )
    except Exception as e:
        log.error("sendDocument error: %s", e)


def show_progress(chat_id, working_message_id, frames):
    import time as _time

    for f in frames:
        call(
            "editMessageText",
            chat_id=chat_id,
            message_id=working_message_id,
            text=f,
        )
        _time.sleep(1.2)


def is_website_request(text):
    low = text.lower()
    keywords = [
        "sayt",
        "website",
        "web site",
        "web sayt",
        "html",
        "sahifa",
        "ilova",
        "app yarat",
        "sayt yarat",
        "website yarat",
    ]
    return any(k in low for k in keywords)


def is_project_request(text):
    low = text.lower()
    keywords = [
        "java",
        "gradle",
        "maven",
        "apk",
        "android",
        "dastur",
        "app",
        "loyiha",
        "program",
        "python dastur",
        "kod yoz",
        "dastur yoz",
    ]
    return any(k in low for k in keywords)


def is_image_request(text):
    low = text.lower()
    keywords = [
        "rasm",
        "rasm chiz",
        "rasm yarat",
        "surat",
        "image",
        "draw",
        "logo",
        "icon",
        "screenshot",
    ]
    return any(k in low for k in keywords)


def build_project(prompt):
    sys_prompt = (
        "Siz professional dasturchisiz. Foydalanuvchi so'roviga mos dastur loyihasi "
        "fayllarini yarating. "
        'JAVOB FAQAT JSON formatda bo\'lsin: {"files":{"fayl_nomi.uz":"kod",...}}. '
        "Fayllar to'liq, ishlaydigan kod bilan bo'lsin. "
        "Java/Gradle/Maven loyihasi uchun build.gradle, settings.gradle, src/Main.java "
        "kabi barcha kerakli fayllarni qo'shing. Boshqa hech narsa yozmang."
    )
    import json as _json

    raw = ask_gemini(prompt, history=[{"role": "user", "text": sys_prompt}])
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = _json.loads(raw[start:end])
        files = data.get("files", {})
        if files:
            return files
    except Exception as e:
        log.error("build_project json error: %s", e)
    return None


def make_zip(files):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def build_website(prompt):
    sys_prompt = (
        "Siz professional web dasturchisiz. Foydalanuvchi so'roviga mos, "
        "zamonaviy va chiroyli bitta to'liq HTML sahifa yarating. "
        "Sahifa quyidagilarni o'z ichiga olishi kerak:\n"
        "- CSS animatsiyalar (hover, fade, slide, pulse)\n"
        "- Responsive dizayn\n"
        "- Zamonaviy gradientlar va soyali kartalar\n"
        "- Professional shriftlar\n"
        "JAVOB FAQAT HTML KOD bo'lsin (DOCTYPE dan </html> gacha). "
        "Hech qanday izoh yoki tushuntirish yozmang."
    )
    return ask_gemini(prompt, history=[{"role": "user", "text": sys_prompt}])


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
                if is_website_request(text) and not is_project_request(text):
                    prog = call(
                        "sendMessage",
                        chat_id=chat_id,
                        text="Sayt yaratilmoqda...",
                    )
                    if prog and prog.get("ok"):
                        mid = prog["result"]["message_id"]
                        send_typing(chat_id)
                        html_code = build_website(text)
                        show_progress(
                            chat_id,
                            mid,
                            [
                                "Sayt tayyorlanmoqda... (0%)",
                                "Dizayn yaratilmoqda... (40%)",
                                "Animatsiyalar qo'shilmoqda... (70%)",
                                "Tezkorlik tekshirilmoqda... (90%)",
                            ],
                        )
                        if html_code.startswith("AI xato") or html_code.startswith("Afrik"):
                            call(
                                "editMessageText",
                                chat_id=chat_id,
                                message_id=mid,
                                text=f"Sayt yaratishda xatolik: {html_code}",
                            )
                        else:
                            import io

                            name = "sayt.html"
                            if "```" in html_code:
                                html_code = html_code.split("```")[1]
                                if html_code.startswith("html"):
                                    html_code = html_code[4:]
                            try:
                                start = html_code.index("<html")
                                end = html_code.rindex("</html>") + len("</html>")
                                html_code = html_code[start:end]
                            except ValueError:
                                pass
                            send_document(
                                chat_id,
                                name,
                                io.BytesIO(html_code.encode("utf-8")),
                                "Sizning saytingiz tayyor! Faylni yuklab oling va brauzerda oching.",
                            )
                            call(
                                "editMessageText",
                                chat_id=chat_id,
                                message_id=mid,
                                text="Sayt tayyor! Quyida fayl:",
                            )
                    else:
                        send_msg(chat_id, ask_gemini(text, chat_history.get(chat_id, [])))
                elif is_project_request(text):
                    prog = call(
                        "sendMessage",
                        chat_id=chat_id,
                        text="Dastur loyihasi yaratilmoqda...",
                    )
                    mid = prog["result"]["message_id"] if prog and prog.get("ok") else None
                    if mid:
                        send_typing(chat_id)
                    files = build_project(text)
                    if files:
                        if mid:
                            show_progress(
                                chat_id,
                                mid,
                                [
                                    "Loyiha tuzilmoqda... (20%)",
                                    "Kod yozilmoqda... (60%)",
                                    "Tekshirilmoqda... (90%)",
                                ],
                            )
                        import io

                        zipped = make_zip(files)
                        send_document(
                            chat_id,
                            "loyiha.zip",
                            io.BytesIO(zipped),
                            "Loyiha tayyor! ZIP faylni yuklab oling.",
                        )
                        if mid:
                            call(
                                "editMessageText",
                                chat_id=chat_id,
                                message_id=mid,
                                text="Loyiha tayyor! Quyida fayl:",
                            )
                    else:
                        if mid:
                            call(
                                "editMessageText",
                                chat_id=chat_id,
                                message_id=mid,
                                text="Loyiha yaratishda xatolik. Qayta urinib ko'ring.",
                            )
                        else:
                            send_msg(chat_id, "Loyiha yaratishda xatolik. Qayta urinib ko'ring.")
                elif is_image_request(text):
                    send_msg(
                        chat_id,
                        "Rasm yaratish uchun hozircha bepul limit yetarli emas. "
                        "Lekin men matnli javob beraman — nimani chizish kerakligini batafsil yozing.",
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
