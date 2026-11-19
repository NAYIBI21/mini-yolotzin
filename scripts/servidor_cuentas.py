"""Servidor de cuentas de Mini Yolotzin para la demostración en clase.

Sirve la página y guarda cuentas (usuario + contraseña), Mis viajes y los reportes
«¿Cómo va ahora?» (vacío / normal / lleno) en una base SQLite en la computadora
donde se ejecuta. La página sigue funcionando sin este
servidor (por ejemplo en GitHub Pages): ahí solo hay perfiles locales.

Uso, desde la raíz del repositorio:
    python scripts/servidor_cuentas.py            # solo en esta computadora
    python scripts/servidor_cuentas.py --wifi     # también celulares en la misma red Wi-Fi

Seguridad:
- La base se guarda FUERA del repositorio (por defecto ~/.mini-yolotzin/cuentas.db).
- Las contraseñas nunca se guardan en texto: solo un hash scrypt con sal aleatoria.
- La sesión es una cookie HttpOnly; en la base solo queda el hash del token.
- Los reportes se guardan sin usuario (anónimos); solo se pueden enviar con sesión.
- Solo se sirven los archivos públicos de la página (nunca .git, scripts ni la base).
- Con --wifi la conexión es http sin cifrar: úsalo solo en una red de confianza.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import http.server
import json
import mimetypes
import re
import secrets
import socket
import sqlite3
import threading
import time
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = Path.home() / ".mini-yolotzin" / "cuentas.db"

USER_RE = re.compile(r"^[a-z0-9_.-]{3,32}$")
MIN_PASSWORD, MAX_PASSWORD = 8, 128
MAX_BODY = 16_000            # bytes por petición
MAX_TRIPS = 8
SESSION_DAYS = 7
MAX_FAILURES, LOCK_SECONDS = 5, 60
COOKIE = "my_sesion"
PUBLIC_EXT = {".html", ".js", ".css", ".json", ".webmanifest", ".png", ".svg", ".ico", ".csv"}
PUBLIC_DIRS = {"", "icons", "assets"}
REPORT_LEVELS = ("vacio", "normal", "lleno")
REPORT_WINDOW = 30 * 60        # se muestran los reportes de los últimos 30 minutos
REPORT_COOLDOWN = 10 * 60      # una persona puede reportar la misma estación cada 10 minutos
SCRYPT = {"n": 2 ** 14, "r": 8, "p": 1, "dklen": 32}


# ---------- Contraseñas y base de datos ----------

def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, **SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
        expected = hash_password(password, bytes.fromhex(salt_hex)).split("$")[2]
    except ValueError:
        return False
    return hmac.compare_digest(expected, digest_hex)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class Store:
    """Acceso a SQLite. Una conexión por operación: sencillo y seguro entre hilos."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS usuarios (
                    usuario TEXT PRIMARY KEY,
                    clave_hash TEXT NOT NULL,
                    viajes TEXT NOT NULL DEFAULT '[]',
                    creado TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reportes (
                    estacion TEXT NOT NULL,
                    linea TEXT NOT NULL,
                    nivel TEXT NOT NULL,
                    creado REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS reportes_estacion ON reportes (estacion, linea, creado);
                CREATE TABLE IF NOT EXISTS sesiones (
                    token_hash TEXT PRIMARY KEY,
                    usuario TEXT NOT NULL REFERENCES usuarios(usuario) ON DELETE CASCADE,
                    expira REAL NOT NULL
                );
            """)

    def _db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA foreign_keys = ON")
        return db

    def create_user(self, usuario: str, password: str) -> bool:
        try:
            with self._db() as db:
                db.execute("INSERT INTO usuarios (usuario, clave_hash, creado) VALUES (?, ?, ?)",
                           (usuario, hash_password(password), time.strftime("%Y-%m-%dT%H:%M:%S")))
            return True
        except sqlite3.IntegrityError:
            return False

    def verify(self, usuario: str, password: str) -> bool:
        with self._db() as db:
            row = db.execute("SELECT clave_hash FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        if row is None:
            hash_password(password)   # mismo tiempo de respuesta exista o no el usuario
            return False
        return check_password(password, row[0])

    def new_session(self, usuario: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("DELETE FROM sesiones WHERE expira < ?", (time.time(),))
            db.execute("INSERT INTO sesiones VALUES (?, ?, ?)",
                       (token_hash(token), usuario, time.time() + SESSION_DAYS * 86400))
        return token

    def session_user(self, token: str | None) -> str | None:
        if not token:
            return None
        with self._db() as db:
            row = db.execute("SELECT usuario FROM sesiones WHERE token_hash = ? AND expira > ?",
                             (token_hash(token), time.time())).fetchone()
        return row[0] if row else None

    def end_session(self, token: str | None) -> None:
        if token:
            with self._db() as db:
                db.execute("DELETE FROM sesiones WHERE token_hash = ?", (token_hash(token),))

    def get_trips(self, usuario: str) -> list:
        with self._db() as db:
            row = db.execute("SELECT viajes FROM usuarios WHERE usuario = ?", (usuario,)).fetchone()
        return json.loads(row[0]) if row else []

    def set_trips(self, usuario: str, trips: list) -> None:
        with self._db() as db:
            db.execute("UPDATE usuarios SET viajes = ? WHERE usuario = ?",
                       (json.dumps(trips, ensure_ascii=False), usuario))


    def add_report(self, estacion: str, linea: str, nivel: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM reportes WHERE creado < ?", (time.time() - 7 * 86400,))
            db.execute("INSERT INTO reportes VALUES (?, ?, ?, ?)", (estacion, linea, nivel, time.time()))

    def report_summary(self, estacion: str, linea: str) -> dict:
        since = time.time() - REPORT_WINDOW
        with self._db() as db:
            rows = db.execute("SELECT nivel, COUNT(*), MAX(creado) FROM reportes "
                              "WHERE estacion = ? AND linea = ? AND creado >= ? GROUP BY nivel",
                              (estacion, linea, since)).fetchall()
        counts = {level: 0 for level in REPORT_LEVELS}
        last = 0.0
        for nivel, count, newest in rows:
            counts[nivel] = count
            last = max(last, newest)
        total = sum(counts.values())
        return {**counts, "total": total, "minutos": round((time.time() - last) / 60) if total else None,
                "ventana": REPORT_WINDOW // 60}


def valid_trips(value) -> bool:
    """Mis viajes: lista corta de objetos simples (lo que guarda la página)."""
    if not isinstance(value, list) or len(value) > MAX_TRIPS:
        return False
    for trip in value:
        if not isinstance(trip, dict) or not isinstance(trip.get("id"), str):
            return False
        for stop in (trip.get("from"), trip.get("to")):
            if stop is not None and not (isinstance(stop, dict) and isinstance(stop.get("name"), str)
                                         and isinstance(stop.get("line"), str)):
                return False
        if not isinstance(trip.get("label", ""), str) or len(trip.get("label", "")) > 60:
            return False
    return True


# ---------- Servidor http ----------

class Limiter:
    """Bloquea un usuario un minuto tras 5 intentos fallidos seguidos."""

    def __init__(self):
        self.lock = threading.Lock()
        self.failures: dict[str, tuple[int, float]] = {}

    def blocked(self, key: str) -> bool:
        with self.lock:
            count, since = self.failures.get(key, (0, 0.0))
            if count >= MAX_FAILURES and time.time() - since < LOCK_SECONDS:
                return True
            if count >= MAX_FAILURES:
                self.failures.pop(key, None)
            return False

    def fail(self, key: str) -> None:
        with self.lock:
            count, _ = self.failures.get(key, (0, 0.0))
            self.failures[key] = (count + 1, time.time())

    def reset(self, key: str) -> None:
        with self.lock:
            self.failures.pop(key, None)


def make_handler(store: Store, root: Path = ROOT, secure_cookie: bool = False):
    limiter = Limiter()
    recent_reports: dict[tuple[str, str, str], float] = {}   # solo en memoria: quién reportó qué y cuándo
    reports_lock = threading.Lock()

    class Handler(http.server.BaseHTTPRequestHandler):
        server_version = "MiniYolotzin"
        sys_version = ""

        def log_message(self, fmt, *args):   # sin registrar contraseñas ni rutas
            pass

        # --- utilidades ---
        def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "same-origin")
            self.send_header("X-Mini-Yolotzin-Cuentas", "1")   # la página lo usa para saber que hay cuentas
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status: int, payload, extra: dict | None = None):
            headers = {"Cache-Control": "no-store", **(extra or {})}
            self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8", headers)

        def _token(self) -> str | None:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            return cookie[COOKIE].value if COOKIE in cookie else None

        def _cookie(self, token: str, max_age: int) -> dict:
            flags = f"{COOKIE}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={max_age}"
            return {"Set-Cookie": flags + ("; Secure" if secure_cookie else "")}

        def _body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length <= 0 or length > MAX_BODY:
                return None
            if "application/json" not in self.headers.get("Content-Type", ""):
                return None
            try:
                return json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                return None

        def _same_origin(self) -> bool:
            """Frena peticiones enviadas desde otras páginas (CSRF)."""
            origin = self.headers.get("Origin")
            return origin is None or urlparse(origin).netloc == self.headers.get("Host")

        # --- archivos de la página ---
        def _static(self):
            path = unquote(urlparse(self.path).path)
            if path.endswith("/"):
                path += "index.html"
            parts = [p for p in path.split("/") if p]
            if any(p.startswith(".") for p in parts) or "/".join(parts[:-1]) not in PUBLIC_DIRS:
                return self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            file = (root / "/".join(parts)).resolve()
            if root.resolve() not in file.parents or file.suffix not in PUBLIC_EXT or not file.is_file():
                return self._send(404, b"No encontrado", "text/plain; charset=utf-8")
            ctype = "application/manifest+json" if file.suffix == ".webmanifest" else (
                mimetypes.guess_type(file.name)[0] or "application/octet-stream")
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self._send(200, file.read_bytes(), ctype, {"Cache-Control": "no-cache"})

        # --- rutas ---
        def do_HEAD(self):
            self.do_GET()

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/api/estado":
                return self._json(200, {"cuentas": True, "usuario": store.session_user(self._token())})
            if route == "/api/viajes":
                user = store.session_user(self._token())
                return self._json(200, {"viajes": store.get_trips(user)}) if user else \
                    self._json(401, {"error": "Inicia sesión."})
            if route == "/api/reportes":
                query = parse_qs(urlparse(self.path).query)
                estacion = (query.get("estacion") or [""])[0][:60]
                linea = (query.get("linea") or [""])[0][:3]
                if not estacion or not linea:
                    return self._json(400, {"error": "Indica estación y línea."})
                return self._json(200, store.report_summary(estacion, linea))
            if route.startswith("/api/"):
                return self._json(404, {"error": "No encontrado."})
            self._static()

        def do_POST(self):
            route = urlparse(self.path).path
            if not self._same_origin():
                return self._json(403, {"error": "Origen no permitido."})
            if route == "/api/salir":
                store.end_session(self._token())
                return self._json(200, {"ok": True}, self._cookie("", 0))
            if route == "/api/reportes":
                return self._report()
            if route not in ("/api/registro", "/api/entrar"):
                return self._json(404, {"error": "No encontrado."})
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "Petición no válida."})
            usuario = str(data.get("usuario", "")).strip().lower()
            password = str(data.get("contrasena", ""))
            if not USER_RE.match(usuario):
                return self._json(400, {"error": "El usuario debe tener de 3 a 32 letras, números, punto, guion o guion bajo."})
            if not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
                return self._json(400, {"error": f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres."})
            if route == "/api/registro":
                if not store.create_user(usuario, password):
                    return self._json(409, {"error": "Ese usuario ya existe. Elige otro o inicia sesión."})
            else:
                if limiter.blocked(usuario):
                    return self._json(429, {"error": "Demasiados intentos. Espera un minuto."})
                if not store.verify(usuario, password):
                    limiter.fail(usuario)
                    return self._json(401, {"error": "Usuario o contraseña incorrectos."})
                limiter.reset(usuario)
            token = store.new_session(usuario)
            self._json(200, {"usuario": usuario}, self._cookie(token, SESSION_DAYS * 86400))

        def _report(self):
            user = store.session_user(self._token())
            if not user:
                return self._json(401, {"error": "Inicia sesión para reportar."})
            data = self._body()
            if not isinstance(data, dict):
                return self._json(400, {"error": "Petición no válida."})
            estacion, linea, nivel = (str(data.get(k, "")).strip() for k in ("estacion", "linea", "nivel"))
            if nivel not in REPORT_LEVELS or not 0 < len(estacion) <= 60 or not 0 < len(linea) <= 3:
                return self._json(400, {"error": "Reporte no válido."})
            key, now = (user, estacion, linea), time.time()
            with reports_lock:
                if now - recent_reports.get(key, 0) < REPORT_COOLDOWN:
                    return self._json(429, {"error": "Ya reportaste esta estación hace poco. Gracias."})
                recent_reports[key] = now
            store.add_report(estacion, linea, nivel)
            self._json(200, store.report_summary(estacion, linea))

        def do_PUT(self):
            if urlparse(self.path).path != "/api/viajes":
                return self._json(404, {"error": "No encontrado."})
            if not self._same_origin():
                return self._json(403, {"error": "Origen no permitido."})
            user = store.session_user(self._token())
            if not user:
                return self._json(401, {"error": "Inicia sesión."})
            data = self._body()
            trips = data.get("viajes") if isinstance(data, dict) else None
            if not valid_trips(trips):
                return self._json(400, {"error": "Viajes no válidos."})
            store.set_trips(user, trips)
            self._json(200, {"ok": True})

    return Handler


def lan_address() -> str:
    """IP de esta computadora en la red local (para abrir la página desde el celular)."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Servidor de cuentas de Mini Yolotzin (demo en clase).")
    parser.add_argument("--wifi", action="store_true", help="aceptar celulares de la misma red Wi-Fi")
    parser.add_argument("--puerto", type=int, default=8000)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help=f"archivo de la base (por defecto {DEFAULT_DB})")
    args = parser.parse_args()
    if ROOT in args.db.resolve().parents:
        parser.error("La base no puede quedar dentro del repositorio: elige otra ruta con --db.")
    store = Store(args.db)
    host = "0.0.0.0" if args.wifi else "127.0.0.1"
    server = http.server.ThreadingHTTPServer((host, args.puerto), make_handler(store))
    print(f"Mini Yolotzin con cuentas · base: {args.db}")
    print(f"  En esta computadora: http://localhost:{args.puerto}/")
    if args.wifi:
        print(f"  Desde un celular en la misma red Wi-Fi: http://{lan_address()}:{args.puerto}/")
        print("  Aviso: la conexión no está cifrada; úsalo solo en una red de confianza.")
    print("Ctrl+C para detener.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
