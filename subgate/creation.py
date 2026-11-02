"""Telegram Mini App deployment with signed identity and expiring login state."""
import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit
from aiohttp import web

KINDS = ("forcesubs", "payment", "userbot")


def telegram_identity(raw, token, now=None):
    if not isinstance(raw, str) or len(raw) > 12000: raise PermissionError("Buka formulir dari bot induk.")
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    data = dict(pairs)
    if len(data) != len(pairs): raise PermissionError("Identitas tidak valid.")
    signature = data.pop("hash", "")
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    check = "\n".join(f"{k}={v}" for k,v in sorted(data.items()))
    expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected): raise PermissionError("Identitas Telegram tidak valid.")
    stamp = int(data.get("auth_date", "0"))
    now = time.time() if now is None else now
    if not -30 <= now-stamp <= 600: raise PermissionError("Sesimu sudah berakhir. Buka formulir baru dari bot induk.")
    user = json.loads(data.get("user", "{}"))
    if type(user.get("id")) is not int or user["id"] <= 0: raise PermissionError("Identitas Telegram tidak tersedia.")
    return user


@dataclass
class Session:
    owner: int
    name: str
    token: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    touched: float = field(default_factory=time.monotonic)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    step: str = "choose"
    kind: str = ""
    api_id: int = 0
    api_hash: str = ""
    login: object = None
    identity: dict = field(default_factory=dict)
    bot_token: str = ""
    result: dict = field(default_factory=dict)


class Creation:
    def __init__(self, db, manager, bot_token, public_base, helper, bind="127.0.0.1", port=8081, login_factory=None):
        self.db, self.manager, self.bot_token = db, manager, bot_token
        self.public_base, self.helper, self.bind, self.port = public_base.rstrip("/"), helper, bind, port
        if self.public_base:
            url = urlsplit(self.public_base)
            if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
                raise ValueError("CREATION_PUBLIC_BASE harus berupa origin HTTPS tanpa path.")
        self.login_factory = login_factory
        self.notifier = None
        self.sessions, self.by_owner, self.auth_lock = {}, {}, asyncio.Lock()
        self.runner = self.cleanup_task = None
        self.app = web.Application(client_max_size=16000, middlewares=[self.errors])
        self.app.router.add_get("/", self.page)
        self.app.router.add_get("/app.js", self.script)
        self.app.router.add_get("/style.css", self.style)
        self.app.router.add_post("/api/auth", self.auth)
        self.app.router.add_post("/api/action", self.action)

    @web.middleware
    async def errors(self, request, handler):
        try:
            origin = request.headers.get("Origin")
            if origin and self.public_base and origin != self.public_base: raise PermissionError("Origin tidak sesuai.")
            response = await handler(request)
        except (PermissionError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            # Only our own validation messages are safe to display.
            message = str(exc) if isinstance(exc, PermissionError) else "Periksa data dan langkah formulirmu, lalu coba lagi."
            response = web.json_response({"error": message}, status=403 if isinstance(exc, PermissionError) else 400)
        except asyncio.CancelledError:
            raise
        except Exception:
            response = web.json_response({"error": "Belum berhasil terhubung. Periksa koneksi dan data login, lalu coba lagi."}, status=502)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; form-action 'none'"})
        return response

    async def asset(self, name, content_type):
        return web.Response(text=(Path(__file__).parent / "web" / name).read_text(encoding="utf-8"), content_type=content_type)

    async def page(self, request): return await self.asset("index.html", "text/html")
    async def script(self, request): return await self.asset("app.js", "text/javascript")
    async def style(self, request): return await self.asset("style.css", "text/css")

    def view(self, session):
        record = self.manager.userbots.record(session.owner) if self.manager.userbots else None
        return {"step": session.step, "kind": session.kind, "name": session.name, "identity": session.identity,
                "kinds": [k for k in KINDS if self.db.allowed(session.owner,k)], "existing": bool(record), "result": session.result,
                "helper": self.helper}

    async def auth(self, request):
        data = await request.json()
        user = telegram_identity(data.get("initData"), self.bot_token)
        owner = user["id"]
        if not any(self.db.allowed(owner,k) for k in KINDS): raise PermissionError("Izinmu sudah tidak aktif.")
        async with self.auth_lock:
            old = self.sessions.get(self.by_owner.get(owner))
            if old and time.monotonic()-old.touched <= 600:
                async with old.lock:
                    return web.json_response({"token": old.token, **self.view(old)})
            if old:
                async with old.lock: await self.discard(old)
            session = Session(owner, " ".join(user.get(x, "") for x in ("first_name", "last_name")).strip())
            self.sessions[session.token] = session
            self.by_owner[owner] = session.token
            return web.json_response({"token": session.token, **self.view(session)})

    async def discard(self, session):
        self.sessions.pop(session.token, None)
        if self.by_owner.get(session.owner) == session.token: self.by_owner.pop(session.owner, None)
        if session.login:
            await session.login.close(discard=session.step != "done")
            session.login = None
        session.api_hash = session.bot_token = ""

    async def action(self, request):
        bearer = request.headers.get("Authorization", "")
        session = self.sessions.get(bearer.removeprefix("Bearer ")) if bearer.startswith("Bearer ") else None
        if not session: raise PermissionError("Sesimu sudah berakhir. Buka formulir dari bot induk.")
        data = await request.json()
        async with session.lock:
            if session.token not in self.sessions or time.monotonic()-session.touched > 600:
                await self.discard(session)
                raise PermissionError("Tidak ada aktivitas selama 10 menit. Buka formulir baru dari bot induk.")
            if not any(self.db.allowed(session.owner,k) for k in KINDS) or (session.kind and not self.db.allowed(session.owner,session.kind)):
                await self.discard(session)
                raise PermissionError("Izin penggunaanmu sudah dicabut.")
            session.touched = time.monotonic()
            action = data.get("action")
            if action == "status": return web.json_response(self.view(session))
            if action == "new" and session.step == "done":
                session.step, session.kind = "choose", ""
                session.api_id, session.api_hash, session.bot_token = 0, "", ""
                session.identity, session.result = {}, {}
                return web.json_response(self.view(session))
            if action == "cancel" and session.step == "done": return web.json_response(self.view(session))
            if action == "cancel":
                await self.discard(session)
                return web.json_response({"step": "cancelled", "helper": self.helper})
            if action == "back" and session.step in ("api","phone","token","otp","password","summary"):
                if session.login:
                    await session.login.close(discard=True)
                    session.login = None
                old = session.step
                session.identity, session.bot_token = {}, ""
                if old == "api": session.kind, session.step = "", "choose"
                elif old in ("phone","token"): session.step = "api"
                else: session.step = "phone" if session.kind == "userbot" else "token"
            elif action == "choose" and session.step == "choose":
                kind = data.get("kind")
                if kind not in KINDS or not self.db.allowed(session.owner,kind): raise PermissionError("Layanan ini belum diizinkan.")
                session.kind, session.step = kind, "api"
            elif action == "api" and session.step == "api":
                from zei_userbot.login import validate_api
                validate_api(data.get("api_id"), data.get("api_hash"))
                session.api_id, session.api_hash = data["api_id"], data["api_hash"]
                session.step = "phone" if session.kind == "userbot" else "token"
            elif action == "phone" and session.step == "phone":
                if session.login: await session.login.close(discard=True)
                if self.login_factory is None:
                    from zei_userbot.login import Login
                    factory = Login
                else: factory = self.login_factory
                session.login = factory(session.owner, session.api_id, session.api_hash)
                async with asyncio.timeout(60): await session.login.begin(data.get("phone"))
                session.step = "otp"
            elif action in ("otp", "password") and session.step == action:
                async with asyncio.timeout(60):
                    result = await (session.login.code(data.get("code")) if action == "otp" else session.login.password(data.get("password")))
                session.step = result["step"]
                if session.step == "summary": session.identity = {k:v for k,v in result.items() if k != "step"}
            elif action == "token" and session.step == "token":
                from .telegram import TOKEN
                token = data.get("token", "")
                if not TOKEN.fullmatch(token): raise ValueError("Token belum sesuai.")
                identity, _ = await self.manager.authenticate(session.api_id, session.api_hash, token)
                if identity["id"] == self.manager.master_bot_id: raise PermissionError("Gunakan token bot yang ingin kamu buat.")
                existing = self.db.rows("SELECT owner,kind FROM bots WHERE id=?", (identity["id"],))
                if existing and (existing[0]["owner"] != session.owner or existing[0]["kind"] != session.kind):
                    raise PermissionError("Bot ini sudah terdaftar dan tidak dapat diambil alih atau diganti jenisnya.")
                session.bot_token, session.identity, session.step = token, identity, "summary"
            elif action == "create":
                if session.step == "done": return web.json_response(self.view(session))
                if session.step != "summary": raise ValueError("Lengkapi login terlebih dahulu.")
                if session.kind == "userbot":
                    async with self.manager.lock:
                        if not self.db.allowed(session.owner,"userbot"): raise PermissionError("Izinmu sudah dicabut.")
                        credentials = session.login.credentials()
                        await self.manager.userbots.deploy(session.owner, credentials, session.identity)
                        session.step = "done"
                    await session.login.close()
                    session.login = None
                    session.result = {"name": session.identity["name"], "username": session.identity.get("username", ""), "prefix": self.prefix(session.owner)}
                else:
                    session.result = await self.manager.deploy(session.owner,session.api_id,session.api_hash,session.bot_token,session.kind)
                    session.step = "done"
                session.api_hash = session.bot_token = ""
                if self.notifier:
                    try: await self.notifier(session.owner,session.kind,session.result)
                    except Exception: pass
            else: raise ValueError("Langkah tidak sesuai.")
            return web.json_response(self.view(session))

    def prefix(self, owner):
        from zei_userbot.state import State
        state = State(self.manager.userbots.directory / str(owner) / "settings.sqlite")
        try: return state.prefix
        finally: state.close()

    async def sweep(self):
        while True:
            await asyncio.sleep(15)
            for session in list(self.sessions.values()):
                if time.monotonic()-session.touched > 600 or not self.db.allowed(session.owner,session.kind or None):
                    async with session.lock:
                        if time.monotonic()-session.touched > 600 or not self.db.allowed(session.owner,session.kind or None):
                            try: await self.discard(session)
                            except Exception: pass

    async def start(self):
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        await web.TCPSite(self.runner,self.bind,self.port).start()
        self.cleanup_task = asyncio.create_task(self.sweep())

    async def close(self):
        if self.cleanup_task:
            self.cleanup_task.cancel()
            await asyncio.gather(self.cleanup_task, return_exceptions=True)
        if self.runner: await self.runner.cleanup()
        for session in list(self.sessions.values()):
            try: await self.discard(session)
            except Exception: pass
