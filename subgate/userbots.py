"""Encrypted account records and isolated worker supervision."""
import asyncio
import json
import os
import sys
from pathlib import Path


class Process:
    def __init__(self, process): self.process = process

    async def stop(self):
        if self.process.returncode is None:
            if self.process.stdin and not self.process.stdin.is_closing(): self.process.stdin.close()
            try: await asyncio.wait_for(self.process.wait(), 10)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()


class Userbots:
    def __init__(self, db, directory, helper="", factory=None):
        self.db, self.directory, self.helper = db, Path(directory), helper
        self.running = {}
        self.factory = factory or self.spawn
        self.notifier = None

    def record(self, owner):
        rows = self.db.rows("SELECT * FROM userbots WHERE owner=?", (owner,))
        return rows[0] if rows else None

    async def spawn(self, owner, credentials):
        folder = self.directory / str(owner)
        folder.mkdir(parents=True, exist_ok=True)
        env = {key:value for key,value in os.environ.items() if key.upper() not in {
            "MASTER_BOT_TOKEN", "MASTER_OWNER_ID", "SECRET_KEY", "PAYMENT_PUBLIC_BASE", "DATA_DIR"}}
        env["PYTHONPATH"] = os.pathsep.join(sys.path)
        process = await asyncio.create_subprocess_exec(sys.executable, "-m", "zei_userbot.worker", stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=env)
        runner = Process(process)
        try:
            process.stdin.write((json.dumps({"owner": owner, "credentials": credentials, "path": str(folder / "settings.sqlite"), "helper": self.helper})+"\n").encode())
            await process.stdin.drain()
            ready = await asyncio.wait_for(process.stdout.readline(), 60)
            if ready.strip() != b"READY": raise ValueError("Userbot belum berhasil terhubung.")
            return runner
        except BaseException:
            await runner.stop()
            raise

    async def deploy(self, owner, credentials, identity):
        if not self.db.allowed(owner, "userbot") or identity.get("id") != owner:
            raise PermissionError("Izin atau identitas akun tidak sesuai.")
        # Verify the replacement before stopping a working session.
        candidate = await self.factory(owner, credentials)
        try:
            if not self.db.allowed(owner, "userbot"): raise PermissionError("Izin sudah dicabut.")
            encrypted = self.db.cipher.encrypt(json.dumps(credentials).encode())
            with self.db.conn:
                self.db.conn.execute("INSERT INTO userbots(owner,name,credentials) VALUES (?,?,?) ON CONFLICT(owner) DO UPDATE SET name=excluded.name,credentials=excluded.credentials,active=1,redeploy_required=0", (owner, identity["name"], encrypted))
        except BaseException:
            await candidate.stop()
            raise
        old = self.running.pop(owner, None)
        self.running[owner] = candidate
        if old: await old.stop()

    async def reconcile(self):
        for owner in list(self.running):
            row = self.record(owner)
            runner = self.running[owner]
            dead = hasattr(runner, "process") and runner.process.returncode is not None
            if dead or not row or not row["active"] or not self.db.allowed(owner, "userbot"):
                await self.running.pop(owner).stop()
                if self.notifier and not self.db.allowed(owner,"userbot"):
                    try: await self.notifier(owner)
                    except Exception: pass
        for row in self.db.rows("SELECT * FROM userbots WHERE active=1 AND redeploy_required=0"):
            owner = row["owner"]
            if owner not in self.running and self.db.allowed(owner, "userbot"):
                try:
                    credentials = json.loads(self.db.cipher.decrypt(row["credentials"]))
                    self.running[owner] = await self.factory(owner, credentials)
                except Exception:
                    # Keep the record for reconnect; never print credentials or RPC payloads.
                    pass

    async def close(self):
        for runner in self.running.values(): await runner.stop()
        self.running.clear()
