"""
G-SYNC · Sincronizador Git profesional, seguro y genérico para cualquier proyecto.
================================================================================

Una ÚNICA herramienta (sync.py), autocontenida, portable y sin dependencias
(solo librería estándar de Python). Cópiala a la raíz de CUALQUIER proyecto y
estará lista para sincronizar con GitHub (o cualquier remoto Git) sin recordar
comandos, con red de seguridad ante errores caros.

USO INTERACTIVO (menú bonito):
    python sync.py

USO DIRECTO (CLI) — comandos principales:
    setup      Asistente: crea repo, remoto, rama y .gitignore.
    status     Estado detallado (cambios, ahead/behind, sparkline).
    dashboard  Panel de estado en una pantalla (--watch para vivo).
    pull       Trae cambios del remoto (rebase, auto-stash, reintentos).
    push       add + commit + push (con escáner de secretos y protección de ramas).
    commit     Crea un commit (modo libre o Conventional Commits guiado).
    save       Guardado rápido (commit automático + push).
    sync       Todo en uno: commit + fetch + rebase + push.
    amend      Corrige el último commit (mensaje o añadir archivos).
    log        Historial bonito con tiempos relativos.
    diff       Cambios pendientes (con barras de diffstat).
    find       Busca en el historial por mensaje (--grep) o por código (-S).
    who        Contribuidores y actividad del repositorio.
    branch     Lista, crea o cambia de rama (tabla).
    stash      Guarda o recupera cambios temporales.
    tag        Crea una etiqueta/versión.
    release    Sube versión semántica + genera CHANGELOG desde los commits.
    pr         Crea un Pull Request (gh o navegador).
    undo       Deshace el último commit (con snapshot de seguridad).
    discard    Descarta cambios locales (con snapshot de seguridad).
    rescue     Recupera trabajo perdido desde el reflog.
    restore    Restaura UN archivo a una versión anterior.
    clone      Clona un repositorio.
    remote     Gestiona los remotos.
    ignore     Crea/actualiza el .gitignore (según el tipo de proyecto).
    hooks      Instala/quita git hooks (validación antes de commit/push).
    watch      MODO AUTOMÁTICO inteligente (debounce + reintentos).
    schedule   Programa la sincronización en el sistema (Windows/Linux/mac).
    history    Muestra el registro de auditoría de sincronizaciones.
    protect    Gestiona reglas de protección de ramas.
    archive    Exporta un .zip del proyecto (sin .git).
    config     Configuración del proyecto/usuario (global, export/import).
    doctor     Diagnóstico completo del entorno (--fix).
    selftest   Auto-tests internos de la herramienta.

OPCIONES GLOBALES:
    -y, --yes          No preguntar: confirma todo automáticamente.
    -n, --dry-run      Simulación: muestra qué haría sin ejecutar cambios.
        --no-color     Desactiva los colores.
    -q, --quiet        Menos mensajes.
        --allow-secrets  Permite commitear aunque se detecten secretos.

CONFIGURACIÓN: se guarda en '.sync.json' (proyecto) y '~/.g-sync/config.json'
(global). La del proyecto tiene prioridad. Variables de entorno: SYNC_REPO_URL,
SYNC_BRANCH.

Requisitos: Git instalado y acceso al repositorio (HTTPS con token o SSH).
Opcional: 'gh' (GitHub CLI) para crear Pull Requests directamente.
"""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import webbrowser
from collections import Counter, deque
from dataclasses import dataclass, asdict, field, fields
from datetime import datetime
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

# La consola de Windows suele usar cp1252 y no admite caracteres de caja ni
# emojis: forzamos UTF-8 en la salida (con reemplazo por si acaso).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

APP_NAME = "G-SYNC"
APP_VERSION = "3.0"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / ".sync.json"
GLOBAL_DIR = Path.home() / ".g-sync"
GLOBAL_CONFIG = GLOBAL_DIR / "config.json"

ENV_REPO_URL = os.environ.get("SYNC_REPO_URL", "").strip()
ENV_BRANCH = os.environ.get("SYNC_BRANCH", "").strip()


# =============================================================================
# 1 · ESTADO GLOBAL DE EJECUCIÓN
# =============================================================================

class Runtime:
    assume_yes: bool = False
    dry_run: bool = False
    quiet: bool = False
    color: bool = True
    allow_secrets: bool = False
    width: int = 62


RT = Runtime()


# =============================================================================
# 2 · CAPA DE INTERFAZ (colores, cajas, tablas, spinner)
# =============================================================================

class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDER = "\033[4m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GREY = "\033[90m"

    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"


def _enable_windows_ansi() -> bool:
    """Activa el procesamiento de secuencias ANSI en la consola de Windows."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        kernel32.SetConsoleMode(handle, mode.value | 0x0004)
        return True
    except Exception:
        return False


def supports_color() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if os.name == "nt":
        return _enable_windows_ansi() or bool(
            os.environ.get("WT_SESSION") or os.environ.get("TERM")
        )
    return True


def supports_unicode() -> bool:
    enc = (getattr(sys.stdout, "encoding", "") or "").lower()
    return "utf" in enc


def ui_width() -> int:
    """Ancho útil adaptado al terminal real."""
    try:
        cols = shutil.get_terminal_size(fallback=(80, 24)).columns
    except Exception:
        cols = 80
    return max(46, min(cols - 2, 100))


def paint(text: str, *colors: str) -> str:
    if not RT.color:
        return text
    return f"{''.join(colors)}{text}{C.RESET}"


def bold(t: str) -> str:
    return paint(t, C.BOLD)


def dim(t: str) -> str:
    return paint(t, C.DIM)


def ok(t: str) -> None:
    print(paint("  ✔ ", C.BRIGHT_GREEN) + t)


def warn(t: str) -> None:
    print(paint("  ⚠ ", C.YELLOW) + t)


def err(t: str) -> None:
    print(paint("  ✖ ", C.RED, C.BOLD) + t)


def info(t: str) -> None:
    if not RT.quiet:
        print(paint("  → ", C.CYAN) + t)


def step(t: str) -> None:
    if not RT.quiet:
        print(paint("  • ", C.BLUE) + dim(t))


def _char_width(ch: str) -> int:
    """Ancho aproximado en columnas de un carácter (emojis ≈ 2)."""
    o = ord(ch)
    if o in (0xFE0F, 0x200D) or unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    if 0x2500 <= o <= 0x259F:          # box drawing + block elements → 1
        return 1
    if o >= 0x1F000:                    # emojis
        return 2
    if 0x2600 <= o <= 0x27BF:           # símbolos misceláneos + dingbats
        return 2
    if 0x2B00 <= o <= 0x2BFF:           # flechas/figuras anchas
        return 2
    return 1


def _visible_len(s: str) -> int:
    """Ancho visible en columnas, ignorando códigos ANSI."""
    out, i = 0, 0
    while i < len(s):
        if s[i] == "\033":
            while i < len(s) and s[i] != "m":
                i += 1
            i += 1
            continue
        out += _char_width(s[i])
        i += 1
    return out


def _clip(s: str, width: int) -> str:
    """Recorta una cadena (ignorando ANSI) a un ancho visible dado."""
    if _visible_len(s) <= width:
        return s
    out, w, i = "", 0, 0
    while i < len(s) and w < width - 1:
        if s[i] == "\033":
            j = i
            while j < len(s) and s[j] != "m":
                j += 1
            out += s[i:j + 1]
            i = j + 1
            continue
        cw = _char_width(s[i])
        if w + cw > width - 1:
            break
        out += s[i]
        w += cw
        i += 1
    return out + "…"


def hr(width: int | None = None) -> None:
    print(paint("─" * (width or ui_width()), C.GREY))


def section(title: str, icon: str = "") -> None:
    print()
    head = f"{icon}  {title}".strip() if icon else title
    width = ui_width()
    pad = max(0, width - _visible_len(head) - 4)
    print(paint("┄┄ ", C.CYAN) + bold(head) + " " + paint("┄" * pad, C.GREY))


def box(title: str, lines: list[str], width: int | None = None,
        color: str = C.BRIGHT_CYAN) -> None:
    """Dibuja una caja con título centrado."""
    width = width or ui_width()
    print()
    print(paint("╭" + "─" * width + "╮", color))
    tw = _visible_len(title)
    left = max(0, (width - tw - 2) // 2)
    right = max(0, width - tw - 2 - left)
    print(paint("│", color) + " " * (left + 1) + bold(title) +
          " " * (right + 1) + paint("│", color))
    print(paint("├" + "─" * width + "┤", color))
    for ln in lines:
        ln = _clip(ln, width - 1)
        pad = max(0, width - _visible_len(ln) - 1)
        print(paint("│", color) + " " + ln + " " * pad + paint("│", color))
    print(paint("╰" + "─" * width + "╯", color))


def table(headers: list[str], rows: list[list[str]], aligns: list[str] | None = None) -> None:
    """Imprime una tabla alineada (consciente de ANSI y emojis)."""
    if not rows:
        return
    cols = len(headers)
    aligns = aligns or ["l"] * cols
    widths = [_visible_len(h) for h in headers]
    for row in rows:
        for i in range(cols):
            widths[i] = max(widths[i], _visible_len(str(row[i])) if i < len(row) else 0)

    def cell(text: str, w: int, align: str) -> str:
        pad = max(0, w - _visible_len(text))
        if align == "r":
            return " " * pad + text
        if align == "c":
            l = pad // 2
            return " " * l + text + " " * (pad - l)
        return text + " " * pad

    header = "  ".join(bold(cell(h, widths[i], aligns[i])) for i, h in enumerate(headers))
    print("  " + header)
    print("  " + paint("─" * (sum(widths) + 2 * (cols - 1)), C.GREY))
    for row in rows:
        line = "  ".join(
            cell(str(row[i]) if i < len(row) else "", widths[i], aligns[i])
            for i in range(cols)
        )
        print("  " + line)


def sparkline(values: list[int]) -> str:
    """Mini gráfica ASCII con bloques (ancho 1 por valor)."""
    blocks = " ▁▂▃▄▅▆▇█"
    if not values:
        return ""
    peak = max(values) or 1
    out = ""
    for v in values:
        idx = int(round(v / peak * (len(blocks) - 1)))
        out += blocks[idx]
    return out


def bar(value: int, total: int, width: int = 20, color: str = C.GREEN) -> str:
    """Barra proporcional."""
    if total <= 0:
        filled = 0
    else:
        filled = int(round(value / total * width))
    filled = max(0, min(width, filled))
    return paint("█" * filled, color) + paint("░" * (width - filled), C.GREY)


class Spinner:
    """Indicador de progreso animado para operaciones lentas (context manager)."""

    FRAMES_UNICODE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    FRAMES_ASCII = ["|", "/", "-", "\\"]

    def __init__(self, message: str):
        self.message = message
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._active = (RT.color and not RT.quiet and sys.stdout.isatty()
                        and not RT.dry_run)
        self._frames = (self.FRAMES_UNICODE if supports_unicode()
                        else self.FRAMES_ASCII)

    def _spin(self) -> None:
        i = 0
        while not self._stop.is_set():
            frame = self._frames[i % len(self._frames)]
            sys.stdout.write("\r" + paint("  " + frame + " ", C.CYAN) + self.message)
            sys.stdout.flush()
            i += 1
            time.sleep(0.09)

    def __enter__(self) -> "Spinner":
        if self._active:
            self._thread = threading.Thread(target=self._spin, daemon=True)
            self._thread.start()
        elif not RT.quiet:
            info(self.message)
        return self

    def __exit__(self, *exc) -> None:
        if self._thread:
            self._stop.set()
            self._thread.join()
            sys.stdout.write("\r" + " " * (_visible_len(self.message) + 6) + "\r")
            sys.stdout.flush()


def prompt(question: str, default: str = "") -> str:
    hint = f" {dim('[' + default + ']')}" if default else ""
    try:
        answer = input(paint("  ? ", C.MAGENTA) + question + hint + " › ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise
    return answer or default


def confirm(question: str, *, default: bool = False) -> bool:
    """Confirmación simple. Respeta --yes."""
    if RT.assume_yes:
        return True
    suffix = paint("[S/n]", C.GREEN) if default else paint("[s/N]", C.YELLOW)
    try:
        answer = input(paint("  ? ", C.MAGENTA) + question + f" {suffix} › ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    if not answer:
        return default
    return answer in {"s", "si", "sí", "y", "yes"}


def confirm_phrase(phrase: str, *, allow_yes: bool = True) -> bool:
    """Exige teclear una frase exacta (para operaciones de alto riesgo).

    Con allow_yes=False, ni siquiera --yes puede saltarse la confirmación
    (se usa para salvaguardas de seguridad como el escáner de secretos).
    """
    if allow_yes and RT.assume_yes:
        return True
    try:
        typed = input(paint("  ! ", C.RED) +
                      f"Escribe {bold(phrase)} para confirmar › ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        return False
    return typed == phrase


def human_size(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def fmt_relative(epoch: int) -> str:
    d = int(time.time()) - int(epoch)
    if d < 0:
        d = 0
    if d < 60:
        return "hace un momento"
    if d < 3600:
        return f"hace {d // 60} min"
    if d < 86400:
        return f"hace {d // 3600} h"
    days = d // 86400
    if days < 30:
        return f"hace {days} día(s)"
    if days < 365:
        return f"hace {days // 30} mes(es)"
    return f"hace {days // 365} año(s)"


def fmt_duration(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


# =============================================================================
# 3 · CONFIGURACIÓN (cascada global + proyecto)
# =============================================================================

@dataclass
class SyncConfig:
    remote: str = ""
    branch: str = ""
    pull_strategy: str = "rebase"          # rebase | merge
    auto_stash: bool = True
    commit_template: str = "Actualización {date}"
    commit_style: str = "libre"            # libre | conventional
    confirm: bool = True
    confirm_level: str = "smart"           # smart | always | never
    watch_interval: int = 300
    watch_debounce: int = 15
    watch_max_retries: int = 5
    protected_branches: list[str] = field(
        default_factory=lambda: ["main", "master", "production"]
    )
    block_direct_push: bool = False
    secret_scan: bool = True
    large_file_warn_mb: int = 5
    large_file_block_mb: int = 95
    backup_keep: int = 10
    log_enabled: bool = True
    schema_version: int = 1


_VALID_KEYS = {f.name for f in fields(SyncConfig)}


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


CONFIG_WARNINGS: list[str] = []


def load_config() -> SyncConfig:
    """Fusiona: defaults → global → proyecto → variables de entorno."""
    data: dict = {}
    if GLOBAL_CONFIG.exists():
        data = _deep_merge(data, _read_json(GLOBAL_CONFIG))
    if CONFIG_FILE.exists():
        data = _deep_merge(data, _read_json(CONFIG_FILE))

    cfg = SyncConfig()
    for key, value in data.items():
        if key in _VALID_KEYS:
            setattr(cfg, key, value)
        else:
            CONFIG_WARNINGS.append(f"clave desconocida en configuración: '{key}' (¿typo?)")

    # Variables de entorno (máxima prioridad si están definidas).
    if ENV_REPO_URL:
        cfg.remote = ENV_REPO_URL
    if ENV_BRANCH:
        cfg.branch = ENV_BRANCH

    _validate_config(cfg)
    return cfg


def _validate_config(cfg: SyncConfig) -> None:
    if cfg.pull_strategy not in ("rebase", "merge"):
        CONFIG_WARNINGS.append(f"pull_strategy inválida ('{cfg.pull_strategy}') → uso 'rebase'.")
        cfg.pull_strategy = "rebase"
    if cfg.commit_style not in ("libre", "conventional"):
        cfg.commit_style = "libre"
    if cfg.confirm_level not in ("smart", "always", "never"):
        cfg.confirm_level = "smart"
    try:
        cfg.watch_interval = max(10, int(cfg.watch_interval))
    except (TypeError, ValueError):
        cfg.watch_interval = 300
    if cfg.remote and not re.match(r"^(https?://|git@|ssh://)", cfg.remote):
        CONFIG_WARNINGS.append(f"la URL del remoto no parece válida: '{cfg.remote}'.")
    try:
        cfg.commit_template.format(date="")
    except (KeyError, IndexError):
        CONFIG_WARNINGS.append("commit_template tiene marcadores no válidos → uso el valor por defecto.")
        cfg.commit_template = "Actualización {date}"


def save_config(cfg: SyncConfig, *, glob: bool = False) -> None:
    target = GLOBAL_CONFIG if glob else CONFIG_FILE
    if RT.dry_run:
        info(f"[simulación] Guardaría configuración en {target}")
        return
    if glob:
        GLOBAL_DIR.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(asdict(cfg), indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


CONFIG = load_config()


# =============================================================================
# 4 · GIT — utilidades base
# =============================================================================

_MUTATING = {
    "init", "add", "commit", "push", "pull", "fetch", "merge", "rebase",
    "reset", "checkout", "switch", "branch", "stash", "clone", "tag",
    "remote", "clean", "restore", "revert", "bundle",
}

_LAST_STDERR = ""


def git_available() -> bool:
    return shutil.which("git") is not None


def run_git(*args: str, check: bool = True, capture: bool = False,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    global _LAST_STDERR
    cmd = ["git", *args]
    subcmd = args[0] if args else ""

    if RT.dry_run and subcmd in _MUTATING and not capture:
        print(paint("  ~ ", C.YELLOW) + dim(f"[simulación] {' '.join(cmd)}"))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if not capture and not RT.quiet:
        print(paint("  $ ", C.GREY) + dim(" ".join(cmd)))

    result = subprocess.run(
        cmd, cwd=str(cwd or SCRIPT_DIR), text=True,
        capture_output=capture, check=check,
        encoding="utf-8", errors="replace",
    )
    if capture and result.stderr:
        _LAST_STDERR = result.stderr
    return result


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_git(*args, check=check)


def git_out(*args: str) -> str:
    res = run_git(*args, check=False, capture=True)
    return (res.stdout or "").strip()


def is_git_repo() -> bool:
    res = run_git("rev-parse", "--is-inside-work-tree", check=False, capture=True)
    return res.returncode == 0 and res.stdout.strip() == "true"


def repo_root() -> Path:
    out = git_out("rev-parse", "--show-toplevel")
    if out:
        try:
            return Path(out)
        except Exception:
            pass
    return SCRIPT_DIR


def current_branch() -> str:
    b = git_out("branch", "--show-current")
    if b:
        return b
    b = git_out("rev-parse", "--abbrev-ref", "HEAD")
    if b and b != "HEAD":
        return b
    return CONFIG.branch or "main"


def remote_url() -> str:
    return git_out("remote", "get-url", "origin")


def configured_remote() -> str:
    return remote_url() or CONFIG.remote or ENV_REPO_URL


def has_changes() -> bool:
    return bool(git_out("status", "--porcelain"))


def has_staged() -> bool:
    return bool(git_out("diff", "--cached", "--name-only"))


def has_commits() -> bool:
    return run_git("rev-parse", "HEAD", check=False, capture=True).returncode == 0


def stash_count() -> int:
    return len([x for x in git_out("stash", "list").splitlines() if x.strip()])


def changed_summary() -> tuple[int, int, int]:
    """Devuelve (modificados, sin_seguimiento, en_stage)."""
    modified = untracked = staged = 0
    for line in git_out("status", "--porcelain").splitlines():
        if not line:
            continue
        x, y = line[0], line[1]
        if x == "?" and y == "?":
            untracked += 1
            continue
        if x not in (" ", "?"):
            staged += 1
        if y not in (" ", "?"):
            modified += 1
    return modified, untracked, staged


def ahead_behind() -> tuple[int, int]:
    branch = current_branch()
    res = run_git("rev-list", "--left-right", "--count",
                  f"origin/{branch}...HEAD", check=False, capture=True)
    if res.returncode != 0:
        return 0, 0
    parts = res.stdout.strip().split()
    if len(parts) != 2:
        return 0, 0
    behind, ahead = int(parts[0]), int(parts[1])
    return ahead, behind


def commit_message(template_msg: str = "") -> str:
    if template_msg.strip():
        return template_msg.strip()
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    try:
        return CONFIG.commit_template.format(date=now)
    except (KeyError, IndexError):
        return f"Actualización {now}"


def is_protected(branch: str) -> bool:
    return any(fnmatch.fnmatch(branch, pat) for pat in CONFIG.protected_branches)


# =============================================================================
# 5 · ROBUSTEZ DE RED (errores traducidos, conectividad, reintentos)
# =============================================================================

GIT_ERROR_HINTS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"Authentication failed|could not read Username|Invalid username or password", re.I),
     "Autenticación fallida. En GitHub usa un Personal Access Token como contraseña, o configura SSH."),
    (re.compile(r"non-fast-forward|Updates were rejected|fetch first", re.I),
     "El remoto tiene commits que no tienes. Ejecuta:  python sync.py sync"),
    (re.compile(r"detected dubious ownership", re.I),
     'Windows marca la carpeta como insegura. Ejecuta:\n     git config --global --add safe.directory "'
     + str(SCRIPT_DIR) + '"'),
    (re.compile(r"no upstream|has no upstream|set-upstream|no tracking information", re.I),
     "La rama no tiene upstream. Se añadirá automáticamente con 'push -u'."),
    (re.compile(r"CONFLICT|needs merge|fix conflicts|Merge conflict", re.I),
     "Hay conflictos. Edita los archivos, 'git add' y 'git rebase --continue'."),
    (re.compile(r"Could not resolve host|unable to access|Failed to connect|Connection timed out", re.I),
     "No hay conexión con el remoto. Revisa tu red o la URL del repositorio."),
    (re.compile(r"Permission denied \(publickey\)", re.I),
     "Tu clave SSH no es válida para este remoto. Revisa ~/.ssh o usa HTTPS con token."),
    (re.compile(r"repository not found|does not appear to be a git repository", re.I),
     "El repositorio remoto no existe o no tienes acceso. Revisa la URL con 'remote'."),
    (re.compile(r"pre-commit|pre-push|hook", re.I),
     "Un git hook bloqueó la operación. Revisa el mensaje anterior."),
]

_TRANSIENT = re.compile(
    r"Could not resolve host|Connection timed out|Connection reset|"
    r"TLS|early EOF|RPC failed|Failed to connect|timed out|Temporary failure|"
    r"The remote end hung up", re.I)


def explain_git_error(stderr: str) -> None:
    text = stderr or _LAST_STDERR or ""
    for pattern, hint in GIT_ERROR_HINTS:
        if pattern.search(text):
            print()
            print(paint("  💡 ", C.BRIGHT_YELLOW) + hint)
            return
    if text.strip():
        first = text.strip().splitlines()[0]
        print(dim("     " + first))


def check_connectivity(url: str, timeout: float = 4.0) -> bool:
    """Comprueba conectividad TCP con el host del remoto (no bloqueante largo)."""
    if not url:
        return True
    try:
        if url.startswith("git@"):
            host = url.split("@", 1)[1].split(":", 1)[0]
            port = 22
        else:
            parsed = urlparse(url)
            host = parsed.hostname or ""
            port = parsed.port or (22 if parsed.scheme == "ssh" else 443)
        if not host:
            return True
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def net_git(*args: str, msg: str = "Contactando con el remoto…",
            attempts: int = 3, base: float = 1.5) -> subprocess.CompletedProcess:
    """Ejecuta un comando git de red con spinner y reintentos ante fallos transitorios."""
    if RT.dry_run:
        print(paint("  ~ ", C.YELLOW) + dim(f"[simulación] git {' '.join(args)}"))
        return subprocess.CompletedProcess(["git", *args], 0, "", "")

    last: subprocess.CompletedProcess | None = None
    for i in range(attempts):
        with Spinner(msg if i == 0 else f"{msg} (reintento {i})"):
            res = run_git(*args, check=False, capture=True)
        if res.returncode == 0:
            return res
        last = res
        if i < attempts - 1 and _TRANSIENT.search(res.stderr or ""):
            time.sleep(base * (2 ** i))
            continue
        break

    assert last is not None
    explain_git_error(last.stderr or last.stdout or "")
    raise subprocess.CalledProcessError(
        last.returncode, ["git", *args], last.stdout, last.stderr)


def preflight_remote() -> None:
    """Aviso rápido si no hay conexión con el remoto (no bloquea)."""
    if RT.quiet or RT.dry_run:
        return
    url = configured_remote()
    if url and not check_connectivity(url):
        warn("No se detecta conexión con el remoto; la operación podría tardar o fallar.")


# =============================================================================
# 6 · SEGURIDAD (secretos, archivos grandes, snapshots, protección)
# =============================================================================

SECRET_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("AWS Access Key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{36,}")),
    ("GitHub PAT", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    ("Google API Key", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),
    ("Slack token", re.compile(r"xox[baprs]-[0-9A-Za-z\-]{10,}")),
    ("Clave privada", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}")),
    ("Credencial en variable", re.compile(
        r"(?i)(password|secret|api[_-]?key|token|passwd)\s*[=:]\s*['\"]?[^\s'\"]{6,}")),
]

_SENSITIVE_NAMES = re.compile(r"(^|/)\.env(\.|$)|\.pem$|\.p12$|\.pfx$|id_rsa$|id_dsa$|\.key$", re.I)


def _censor(value: str) -> str:
    value = value.strip()
    if len(value) <= 4:
        return "****"
    return value[:4] + "*" * min(8, len(value) - 4)


def _staged_files() -> list[str]:
    out = git_out("diff", "--cached", "--name-only", "-z")
    return [f for f in out.split("\x00") if f]


def scan_secrets(paths: list[str]) -> list[tuple[str, str, str]]:
    """Devuelve [(archivo, tipo, muestra_censurada)] para posibles secretos en staged."""
    findings: list[tuple[str, str, str]] = []
    for path in paths:
        if _SENSITIVE_NAMES.search(path):
            findings.append((path, "Archivo sensible", "(por nombre)"))
        res = run_git("show", f":{path}", check=False, capture=True)
        content = res.stdout or ""
        if "\x00" in content[:8192]:
            continue  # binario
        content = content[:1_000_000]
        for label, pattern in SECRET_PATTERNS:
            m = pattern.search(content)
            if m:
                findings.append((path, label, _censor(m.group(0))))
    return findings


def check_large_files(paths: list[str]) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Devuelve (avisos, bloqueos) con [(archivo, bytes)] por tamaño."""
    root = repo_root()
    warns: list[tuple[str, int]] = []
    blocks: list[tuple[str, int]] = []
    warn_bytes = CONFIG.large_file_warn_mb * 1024 * 1024
    block_bytes = CONFIG.large_file_block_mb * 1024 * 1024
    for path in paths:
        fp = root / path
        try:
            size = fp.stat().st_size
        except OSError:
            continue
        if size >= block_bytes:
            blocks.append((path, size))
        elif size >= warn_bytes:
            warns.append((path, size))
    return warns, blocks


def precommit_guard() -> bool:
    """Escanea el contenido en 'stage' antes de crear el commit. False → abortar."""
    paths = _staged_files()
    if not paths:
        return True

    # Archivos grandes ---------------------------------------------------------
    warns, blocks = check_large_files(paths)
    if warns:
        warn("Archivos grandes en este commit:")
        for p, s in warns:
            print(f"     {paint(human_size(s), C.YELLOW)}  {p}")
    if blocks:
        err(f"Archivos demasiado grandes (≥ {CONFIG.large_file_block_mb} MB), GitHub los rechazaría:")
        for p, s in blocks:
            print(f"     {paint(human_size(s), C.RED)}  {p}")
        if not confirm("¿Commitear de todas formas (no recomendado)?"):
            return False

    # Secretos -----------------------------------------------------------------
    if CONFIG.secret_scan and not RT.allow_secrets:
        findings = scan_secrets(paths)
        if findings:
            print()
            err("Posibles SECRETOS detectados en los cambios:")
            table(["Archivo", "Tipo", "Muestra"],
                  [[f, t, m] for f, t, m in findings])
            print()
            warn("Si son secretos reales, cancela, retíralos y añádelos a .gitignore.")
            info("Para permitirlo explícitamente: añade la opción --allow-secrets")
            # Salvaguarda: ni siquiera -y puede saltarse esto (solo --allow-secrets).
            if not confirm_phrase("SUBIR SECRETOS", allow_yes=False):
                return False
    return True


def _backups_dir() -> Path:
    return repo_root() / ".sync" / "backups"


def make_safety_snapshot(reason: str) -> None:
    """Crea una copia de seguridad (bundle + untracked) antes de algo destructivo."""
    if RT.dry_run:
        info(f"[simulación] Crearía snapshot de seguridad ({reason}).")
        return
    try:
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        bdir = _backups_dir()
        bdir.mkdir(parents=True, exist_ok=True)
        with Spinner("Creando copia de seguridad…"):
            run_git("bundle", "create", str(bdir / f"{ts}.bundle"), "--all",
                    check=False, capture=True)
            # Capturar índice + árbol de trabajo de archivos YA versionados: el
            # bundle --all solo guarda commits, así que sin esto se perderían los
            # cambios sin commitear. 'git stash create' crea un commit-objeto con
            # ellos (sin tocar el árbol) que dejamos respaldado y referenciado.
            wt = git_out("stash", "create")
            if wt:
                run_git("bundle", "create", str(bdir / f"{ts}-worktree.bundle"), wt,
                        check=False, capture=True)
                run_git("update-ref", f"refs/backups/{ts}", wt, check=False, capture=True)
            # Copiar archivos sin seguimiento (el reflog no los recupera).
            untracked = [f for f in git_out(
                "ls-files", "--others", "--exclude-standard").splitlines() if f]
            if untracked:
                root = repo_root()
                snap = bdir / ts
                for rel in untracked:
                    src = root / rel
                    dst = snap / rel
                    try:
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                    except OSError:
                        pass
            head = git_out("rev-parse", "HEAD")
            hist = repo_root() / ".sync" / "history.jsonl"
            hist.parent.mkdir(parents=True, exist_ok=True)
            with hist.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": ts, "op": reason, "head": head}) + "\n")
        _rotate_backups()
        ok(f"Copia de seguridad creada ({reason}).")
    except Exception as exc:  # nunca bloquear la operación por el backup
        warn(f"No se pudo crear la copia de seguridad: {exc}")


def _rotate_backups() -> None:
    bdir = _backups_dir()
    if not bdir.exists():
        return
    bundles = sorted(bdir.glob("*.bundle"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in bundles[CONFIG.backup_keep:]:
        try:
            old.unlink()
        except OSError:
            pass


def risk_of_protected_push(branch: str) -> bool:
    """True si el push a esta rama debe bloquearse por política."""
    return is_protected(branch) and CONFIG.block_direct_push


# =============================================================================
# 7 · AUDITORÍA (log de sesiones automáticas)
# =============================================================================

def _audit_log_path() -> Path:
    return GLOBAL_DIR / "logs" / f"{SCRIPT_DIR.name}.log"


def audit(message: str) -> None:
    if not CONFIG.log_enabled or RT.dry_run:
        return
    try:
        path = _audit_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        # Rotación simple por tamaño (~512 KB).
        if path.exists() and path.stat().st_size > 512 * 1024:
            path.replace(path.with_suffix(".log.1"))
        with path.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}  {message}\n")
    except OSError:
        pass


# =============================================================================
# 8 · REMOTO / helpers de commit
# =============================================================================

def ensure_remote(interactive: bool = True) -> bool:
    if remote_url():
        return True
    url = CONFIG.remote or ENV_REPO_URL
    if not url and interactive and sys.stdin and sys.stdin.isatty() and not RT.assume_yes:
        section("Configuración del remoto", "🔗")
        print("  Introduce la URL del repositorio remoto:")
        print(dim("    HTTPS → https://github.com/usuario/proyecto.git"))
        print(dim("    SSH   → git@github.com:usuario/proyecto.git"))
        print()
        try:
            url = prompt("URL del repositorio")
        except (KeyboardInterrupt, EOFError):
            return False
    if not url:
        warn("No hay ningún remoto configurado. Usa 'setup' o 'remote' para añadirlo.")
        return False
    CONFIG.remote = url
    save_config(CONFIG)
    git("remote", "add", "origin", url)
    ok(f"Remoto 'origin' configurado: {bold(url)}")
    return True


def create_commit(message: str, *, silent: bool = False) -> bool:
    """add -A + barrera de seguridad + commit."""
    if not has_changes():
        if not silent:
            info("No hay cambios nuevos que confirmar.")
        return False
    if not silent:
        section("Crear commit", "📝")
    git("add", "-A")
    if not has_staged():
        info("No hay cambios para confirmar.")
        return False

    if not precommit_guard():
        run_git("reset", check=False, capture=True)  # vacía el índice; los cambios siguen en el árbol
        warn("Commit cancelado por la barrera de seguridad. No se ha guardado nada.")
        return False

    if not silent:
        print(f"  {dim('Mensaje:')} {bold(message)}")
    git("commit", "-m", message)
    if not silent:
        ok("Commit creado correctamente.")
    return True


CC_TYPES = [
    ("feat", "✨", "Una nueva funcionalidad"),
    ("fix", "🐛", "Corrección de un error"),
    ("docs", "📝", "Cambios en documentación"),
    ("style", "🎨", "Formato (sin cambios de código)"),
    ("refactor", "♻️", "Refactorización"),
    ("perf", "⚡", "Mejora de rendimiento"),
    ("test", "✅", "Añadir o corregir tests"),
    ("build", "📦", "Sistema de build o dependencias"),
    ("ci", "🔧", "Integración continua"),
    ("chore", "🧹", "Tareas de mantenimiento"),
]


def build_conventional_message() -> str:
    """Asistente interactivo de Conventional Commits."""
    section("Commit convencional", "🧩")
    for i, (t, icon, desc) in enumerate(CC_TYPES, 1):
        print(f"  {paint(str(i).rjust(2), C.BRIGHT_CYAN)}  {icon}  {bold(t)}  {dim('· ' + desc)}")
    print()
    try:
        choice = prompt("Tipo de cambio (número)", default="1")
        idx = int(choice) - 1
        if not (0 <= idx < len(CC_TYPES)):
            idx = 0
    except (ValueError, KeyboardInterrupt, EOFError):
        idx = 0
    ctype = CC_TYPES[idx][0]

    scope = prompt("Ámbito/scope (opcional, ej. api, ui)").strip()
    desc = prompt("Descripción corta (imperativo)").strip()
    while not desc:
        desc = prompt("La descripción no puede estar vacía").strip()
    if len(desc) > 72:
        warn("La descripción es larga (>72). Considera acortarla.")
    breaking = confirm("¿Es un cambio que rompe compatibilidad (breaking change)?")

    header = f"{ctype}"
    if scope:
        header += f"({scope})"
    if breaking:
        header += "!"
    header += f": {desc}"
    if breaking:
        detail = prompt("Describe el breaking change").strip()
        header += f"\n\nBREAKING CHANGE: {detail or desc}"
    return header


# =============================================================================
# 9 · ACCIONES (comandos)
# =============================================================================

def cmd_setup(args) -> bool:
    box(f"{APP_NAME} · Asistente de configuración", [
        dim("  Vamos a preparar este proyecto para sincronizar con Git."),
        f"  {dim('Directorio:')} {SCRIPT_DIR}",
    ])

    section("Repositorio Git", "📁")
    if not is_git_repo():
        info("Este directorio todavía no es un repositorio Git.")
        if not confirm("¿Inicializar un repositorio Git aquí?", default=True):
            warn("Configuración cancelada.")
            return False
        git("init")
        branch = getattr(args, "branch", "") or CONFIG.branch or "main"
        git("branch", "-M", branch)
        ok("Repositorio Git inicializado.")
    else:
        ok("Ya es un repositorio Git.")

    section("Repositorio remoto", "🔗")
    existing = remote_url()
    if existing:
        print(f"  Remoto actual: {bold(existing)}")
        new_url = getattr(args, "url", "") or ""
        if not new_url and not RT.assume_yes:
            new_url = prompt("Nueva URL (Enter para conservar la actual)")
        if new_url and new_url != existing:
            if confirm(f"¿Cambiar origin a '{new_url}'?", default=True):
                git("remote", "set-url", "origin", new_url)
                CONFIG.remote = new_url
                ok("Remoto actualizado.")
        else:
            CONFIG.remote = existing
    else:
        url = getattr(args, "url", "") or CONFIG.remote or ENV_REPO_URL
        if not url and not RT.assume_yes:
            print(dim("    Ejemplo: https://github.com/usuario/proyecto.git"))
            url = prompt("URL del repositorio remoto (Enter para omitir)")
        if url:
            git("remote", "add", "origin", url)
            CONFIG.remote = url
            ok(f"Remoto 'origin' añadido: {bold(url)}")
        else:
            warn("No se ha configurado ningún remoto (podrás hacerlo después).")

    section("Rama principal", "🌿")
    branch = getattr(args, "branch", "") or CONFIG.branch or current_branch() or "main"
    if not getattr(args, "branch", "") and not RT.assume_yes:
        branch = prompt("Rama principal", default=branch)
    if is_git_repo() and current_branch() != branch:
        if confirm(f"¿Usar '{branch}' como rama principal?", default=True):
            git("branch", "-M", branch)
    CONFIG.branch = branch

    section("Identidad de Git", "🪪")
    if not git_out("config", "user.name") or not git_out("config", "user.email"):
        warn("No tienes configurada tu identidad de Git.")
        if not RT.assume_yes and confirm("¿Configurarla ahora?", default=True):
            name = prompt("Tu nombre")
            email = prompt("Tu email")
            if name:
                git("config", "--global", "user.name", name)
            if email:
                git("config", "--global", "user.email", email)
            ok("Identidad configurada.")
    else:
        ok(f"Identidad: {git_out('config', 'user.name')} <{git_out('config', 'user.email')}>")

    section("Archivo .gitignore", "📄")
    gitignore = SCRIPT_DIR / ".gitignore"
    if gitignore.exists():
        ok(".gitignore ya existe.")
    elif confirm("¿Crear un .gitignore recomendado?", default=True):
        _write_gitignore()

    save_config(CONFIG)
    box("✔ Configuración guardada", [
        f"  {dim('Proyecto :')} {bold(SCRIPT_DIR.name)}",
        f"  {dim('Remoto   :')} {configured_remote() or paint('(sin configurar)', C.YELLOW)}",
        f"  {dim('Rama     :')} {current_branch()}",
        f"  {dim('Config   :')} {CONFIG_FILE.name}",
    ], color=C.BRIGHT_GREEN)
    print()
    info("La primera vez que subas, Git te pedirá autenticación (usa un token en GitHub).")
    ok("¡Listo! Prueba: " + bold("python sync.py status"))
    return True


def _recent_activity(days: int = 14) -> list[int]:
    out = git_out("log", f"--since={days} days ago",
                  "--pretty=%cd", "--date=format:%Y-%m-%d")
    counts = Counter(l for l in out.splitlines() if l)
    today = datetime.now().date()
    from datetime import timedelta
    series = []
    for i in range(days - 1, -1, -1):
        day = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        series.append(counts.get(day, 0))
    return series


def cmd_status(_args) -> bool:
    branch = current_branch()
    remote = configured_remote()
    modified, untracked, staged = changed_summary()
    stashes = stash_count()

    lines = [
        f"  {dim('Proyecto')}   {bold(SCRIPT_DIR.name)}",
        f"  {dim('Rama')}       {bold(branch)}" +
        (paint("  🔒 protegida", C.YELLOW) if is_protected(branch) else ""),
        f"  {dim('Remoto')}     {remote or paint('(sin configurar)', C.YELLOW)}",
    ]
    box("📊 Estado del repositorio", lines)

    section("Cambios locales", "📝")
    if not has_changes():
        ok("Árbol de trabajo limpio, sin cambios pendientes.")
    else:
        parts = []
        if staged:
            parts.append(paint(f"{staged} preparado(s)", C.GREEN))
        if modified:
            parts.append(paint(f"{modified} modificado(s)", C.YELLOW))
        if untracked:
            parts.append(paint(f"{untracked} sin seguimiento", C.CYAN))
        print("  " + dim(" · ").join(parts))
        print()
        res = run_git("status", "--short", check=False, capture=True)
        for line in res.stdout.rstrip().splitlines()[:20]:
            print("    " + _colorize_status_line(line))
        extra = len(res.stdout.rstrip().splitlines()) - 20
        if extra > 0:
            print(dim(f"    … y {extra} más"))
    if stashes:
        print()
        info(f"Tienes {bold(str(stashes))} guardado(s) en stash.")

    if remote_url():
        section("Sincronización con el remoto", "🔄")
        ahead, behind = ahead_behind()
        if ahead:
            warn(f"{bold(str(ahead))} commit(s) local(es) pendiente(s) de subir (push).")
        if behind:
            warn(f"{bold(str(behind))} commit(s) remoto(s) pendiente(s) de traer (pull).")
        if not ahead and not behind:
            ok("Local y remoto están sincronizados.")

    if has_commits():
        section("Actividad (últimos 14 días)", "📈")
        series = _recent_activity(14)
        total = sum(series)
        print("  " + paint(sparkline(series), C.BRIGHT_CYAN) +
              dim(f"   {total} commit(s)"))

        section("Últimos commits", "🕑")
        out = git_out("log", "-5", "--pretty=format:%h\x1f%s\x1f%an\x1f%at")
        for line in out.splitlines():
            parts = line.split("\x1f")
            if len(parts) == 4:
                h, subj, an, at = parts
                print(f"  {paint(h, C.YELLOW)} {_clip(subj, ui_width() - 30)} "
                      f"{dim('· ' + an + ' · ' + fmt_relative(int(at)))}")
    return True


def _colorize_status_line(line: str) -> str:
    if len(line) < 2:
        return line
    code = line[:2]
    if "?" in code:
        return paint(line, C.CYAN)
    if code[0] != " ":
        return paint(line, C.GREEN)
    return paint(line, C.YELLOW)


def cmd_dashboard(args) -> bool:
    live = getattr(args, "watch", False)

    def render() -> None:
        if live and RT.color:
            print("\033[2J\033[H", end="")  # limpiar pantalla (solo si hay ANSI)
        cmd_status(args)
        if live:
            print()
            print(dim(f"  ⟳ Actualizando cada 5s · {datetime.now():%H:%M:%S} · Ctrl+C para salir"))

    if not live:
        return cmd_status(args)
    try:
        while True:
            render()
            time.sleep(5)
    except (KeyboardInterrupt, EOFError):
        print()
        info("Panel cerrado.")
    return True


def _auto_stash_wrap(action: Callable[[], bool], reason: str) -> bool:
    stashed = False
    if CONFIG.auto_stash and has_changes():
        info(f"Guardando cambios temporalmente antes de {reason} (auto-stash)…")
        git("stash", "push", "-u", "-m", f"g-sync auto-stash · {reason}")
        stashed = True
    try:
        result = action()
    finally:
        if stashed:
            info("Restaurando tus cambios (auto-stash)…")
            res = run_git("stash", "pop", check=False)
            if res.returncode != 0:
                warn("No se pudieron restaurar automáticamente los cambios del stash.")
                warn("Revisa 'git stash list' y resuélvelo manualmente.")
    return result


def cmd_pull(args) -> bool:
    section("Traer cambios del remoto", "⬇")
    if not ensure_remote():
        return False
    branch = current_branch()
    strategy = "--rebase" if CONFIG.pull_strategy == "rebase" else "--no-rebase"

    print(f"  {dim('Remoto:')} {configured_remote()}")
    print(f"  {dim('Rama  :')} {branch}   {dim('Estrategia:')} {CONFIG.pull_strategy}")

    if has_changes() and not CONFIG.auto_stash:
        warn("Tienes cambios locales sin confirmar; un pull podría causar conflictos.")
        if not confirm("¿Continuar de todas formas?"):
            info("Pull cancelado.")
            return False
    elif not confirm("¿Traer los cambios del remoto?", default=True):
        info("Pull cancelado.")
        return False

    preflight_remote()

    def do_pull() -> bool:
        try:
            net_git("pull", strategy, "origin", branch, msg="Trayendo cambios…")
        except subprocess.CalledProcessError:
            err("El pull no pudo completarse.")
            _print_rebase_help()
            return False
        ok("Cambios descargados correctamente.")
        return True

    return _auto_stash_wrap(do_pull, "traer cambios")


def cmd_commit(args) -> bool:
    section("Commit (sin subir)", "📝")
    if not has_changes():
        info("No hay cambios locales que confirmar.")
        return True
    message = (getattr(args, "message", "") or "").strip()
    guided = getattr(args, "guided", False) or (not message and CONFIG.commit_style == "conventional")
    if not message and guided:
        message = build_conventional_message()
    if not message:
        message = prompt("Mensaje del commit")
        if not message:
            err("El commit necesita un mensaje.")
            return False
    return create_commit(message)


def cmd_push(args) -> bool:
    section("Subir cambios", "⬆")
    if not ensure_remote():
        return False
    branch = current_branch()

    if risk_of_protected_push(branch) and not getattr(args, "force_protected", False):
        err(f"La rama '{bold(branch)}' está protegida contra push directo.")
        info("Crea una rama:  python sync.py branch mi-rama   (o usa --force-protected)")
        return False
    if is_protected(branch):
        warn(f"Vas a subir a la rama protegida '{bold(branch)}'.")

    if has_changes():
        message = (getattr(args, "message", "") or "").strip() or commit_message()
        print(f"  {dim('Se creará el commit:')} {bold(message)}")
        if not confirm(f"¿Crear el commit y subirlo a '{branch}'?", default=True):
            info("Push cancelado.")
            return False
        if not create_commit(message, silent=True):
            return False
        ok(f"Commit creado: {message}")
    elif not has_commits():
        warn("Todavía no existe ningún commit en este repositorio.")
        if not confirm("¿Continuar?"):
            return False
    else:
        ahead, _ = ahead_behind()
        detail = f" ({ahead} pendiente(s))" if ahead else ""
        if not confirm(f"¿Subir los commits locales a '{branch}'{detail}?", default=True):
            info("Push cancelado.")
            return False

    preflight_remote()
    try:
        net_git("push", "-u", "origin", branch, msg="Subiendo cambios…")
    except subprocess.CalledProcessError:
        err("No se pudieron subir los cambios.")
        return False
    ok("Cambios enviados correctamente al remoto. 🚀")
    audit(f"push a {branch}")
    return True


def cmd_save(args) -> bool:
    args.message = (getattr(args, "message", "") or "").strip() or commit_message()
    return cmd_push(args)


def cmd_sync(args) -> bool:
    box("🔄 Sincronización completa", [
        dim("  1. Confirmar cambios locales (commit)"),
        dim("  2. Descargar novedades del remoto (fetch)"),
        dim("  3. Aplicar tus commits encima (rebase/merge)"),
        dim("  4. Subir el resultado (push)"),
    ])
    if not ensure_remote():
        return False
    branch = current_branch()
    print()
    print(f"  {dim('Proyecto:')} {bold(SCRIPT_DIR.name)}   {dim('Rama:')} {bold(branch)}")
    print(f"  {dim('Remoto  :')} {configured_remote()}")

    if has_changes():
        message = (getattr(args, "message", "") or "").strip() or commit_message()
        section("Paso 1 · Confirmar cambios", "📝")
        print(f"  {dim('Commit:')} {bold(message)}")
        if not confirm("¿Guardar estos cambios en un commit?", default=True):
            info("Sincronización cancelada.")
            return False
        if not create_commit(message, silent=True):
            return False
        ok("Cambios confirmados.")
    else:
        info("No hay cambios locales nuevos que confirmar.")

    if not confirm("¿Iniciar la sincronización con el remoto?", default=True):
        info("Sincronización cancelada.")
        return False

    preflight_remote()
    section("Paso 2 · Consultar el remoto", "📡")
    try:
        net_git("fetch", "origin", msg="Consultando el remoto…")
    except subprocess.CalledProcessError:
        err("No se pudo contactar con el remoto.")
        return False

    _, behind = ahead_behind()
    if behind:
        section("Paso 3 · Integrar cambios remotos", "🔀")
        info(f"El remoto tiene {bold(str(behind))} commit(s) nuevo(s).")
        strategy = "--rebase" if CONFIG.pull_strategy == "rebase" else "--no-rebase"
        try:
            net_git("pull", strategy, "origin", branch, msg="Integrando cambios…")
        except subprocess.CalledProcessError:
            err("Conflicto al integrar los cambios remotos.")
            _print_rebase_help()
            return False
    else:
        ok("No hay cambios nuevos en el remoto.")

    section("Paso 4 · Subir cambios", "⬆")
    try:
        net_git("push", "-u", "origin", branch, msg="Subiendo cambios…")
    except subprocess.CalledProcessError:
        err("El push falló. El remoto pudo cambiar durante la sincronización.")
        return False

    print()
    box("✔ Sincronización completada", [
        paint("  Todo tu trabajo está guardado y sincronizado. 🎉", C.BRIGHT_GREEN),
    ], color=C.BRIGHT_GREEN)
    audit(f"sync a {branch}")
    return True


def cmd_amend(args) -> bool:
    section("Corregir el último commit", "✏")
    if not has_commits():
        info("No hay commits que corregir.")
        return True
    ahead, _ = ahead_behind()
    if remote_url() and ahead == 0:
        warn("El último commit ya está subido; corregirlo reescribiría el historial remoto.")
        if not confirm("¿Continuar de todas formas?"):
            return False
    last = git_out("log", "-1", "--pretty=format:%h · %s")
    print(f"  {dim('Último commit:')} {bold(last)}")

    if has_changes():
        if confirm("¿Añadir también los cambios actuales al commit?", default=True):
            git("add", "-A")
            if not precommit_guard():
                run_git("reset", check=False, capture=True)
                return False
    new_msg = (getattr(args, "message", "") or "").strip()
    if not new_msg and not RT.assume_yes:
        new_msg = prompt("Nuevo mensaje (Enter = conservar)")
    if new_msg:
        git("commit", "--amend", "-m", new_msg)
    else:
        git("commit", "--amend", "--no-edit")
    ok("Commit corregido.")
    return True


def cmd_log(args) -> bool:
    section("Historial de commits", "🕑")
    if not has_commits():
        info("Todavía no hay commits.")
        return True
    n = str(getattr(args, "count", 15) or 15)
    color = "--color=always" if RT.color else "--no-color"
    fmt = "%C(yellow)%h%Creset %C(auto)%d%Creset %s %C(dim)· %an · %ar%Creset"
    print(git_out("log", f"-{n}", "--graph", color, f"--pretty=format:{fmt}"))
    return True


def cmd_diff(args) -> bool:
    section("Cambios pendientes", "🔍")
    if not has_changes():
        ok("No hay cambios locales.")
        return True
    numstat = git_out("diff", "HEAD", "--numstat")
    rows = []
    max_changes = 1
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            add, dele, name = parts
            a = int(add) if add.isdigit() else 0
            d = int(dele) if dele.isdigit() else 0
            max_changes = max(max_changes, a + d)
            rows.append((name, a, d))
    if rows:
        for name, a, d in rows[:25]:
            gbar = paint("+" * min(a, 30), C.GREEN)
            rbar = paint("-" * min(d, 30), C.RED)
            clipped = _clip(name, 40)
            padded = clipped + " " * max(0, 40 - _visible_len(clipped))
            print(f"  {padded} {gbar}{rbar} {dim(f'+{a} -{d}')}")
        if len(rows) > 25:
            print(dim(f"  … y {len(rows) - 25} archivo(s) más"))
    if getattr(args, "full", False):
        section("Diferencias completas", "")
        color = "--color=always" if RT.color else "--no-color"
        run_git("--no-pager", "diff", "HEAD", color, check=False)
    else:
        print()
        info("Usa 'python sync.py diff --full' para ver las diferencias línea a línea.")
    return True


def cmd_find(args) -> bool:
    section("Buscar en el historial", "🔎")
    term = (getattr(args, "term", "") or "").strip()
    if not term:
        term = prompt("¿Qué quieres buscar?")
    if not term:
        return True
    mode = getattr(args, "mode", "") or ""
    if not mode and not RT.assume_yes:
        print(dim("  [m] por mensaje de commit   ·   [c] por código cambiado"))
        mode = prompt("Modo", default="m")
    color = "--color=always" if RT.color else "--no-color"
    if mode.startswith("c"):
        out = git_out("log", "-S", term, "--oneline", color)
    else:
        out = git_out("log", "--grep", term, "-i", "--oneline", color)
    if out:
        print(out)
    else:
        info("Sin resultados.")
    return True


def cmd_who(args) -> bool:
    section("Contribuidores", "👥")
    if not has_commits():
        info("Todavía no hay commits.")
        return True
    authors = Counter(l for l in git_out("log", "--pretty=%an").splitlines() if l)
    total = sum(authors.values()) or 1
    rows = []
    for name, count in authors.most_common(15):
        pct = count / total * 100
        rows.append([name, str(count), f"{pct:.0f}%", bar(count, total, 18, C.BRIGHT_CYAN)])
    table(["Autor", "Commits", "%", ""], rows, ["l", "r", "r", "l"])
    print()
    info(f"Total: {bold(str(total))} commits de {bold(str(len(authors)))} autor(es).")
    return True


def cmd_branch(args) -> bool:
    section("Ramas", "🌿")
    current = current_branch()
    branches = [b.strip().lstrip("* ").strip()
                for b in git_out("branch").splitlines() if b.strip()]
    rows = []
    for b in branches:
        mark = paint("→", C.GREEN) if b == current else " "
        last = git_out("log", "-1", b, "--pretty=format:%s") if b else ""
        prot = "🔒" if is_protected(b) else ""
        rows.append([mark, bold(b) if b == current else b, prot, _clip(last, 40)])
    table(["", "Rama", "", "Último commit"], rows)

    target = (getattr(args, "name", "") or "").strip()
    if not target and not RT.assume_yes:
        print()
        print(dim("  Escribe un nombre para crear/cambiar de rama, o Enter para salir."))
        target = prompt("Rama")
    if not target:
        return True

    if target in branches:
        if confirm(f"¿Cambiar a la rama '{target}'?", default=True):
            git("switch", target)
            ok(f"Ahora estás en '{target}'.")
    else:
        if confirm(f"La rama '{target}' no existe. ¿Crearla y cambiar a ella?", default=True):
            git("switch", "-c", target)
            ok(f"Rama '{target}' creada.")
    return True


def cmd_stash(args) -> bool:
    section("Guardado temporal (stash)", "📦")
    stashes = git_out("stash", "list")
    action = getattr(args, "action", "") or ""

    if stashes:
        rows = [[f"[{i}]", _clip(line.split(": ", 1)[-1], 50)]
                for i, line in enumerate(stashes.splitlines())]
        table(["Índice", "Descripción"], rows)
        print()
    else:
        info("No hay nada guardado en el stash.")

    if not action and not RT.assume_yes:
        print(dim("  Acciones: [g] guardar  ·  [r] recuperar  ·  [Enter] salir"))
        choice = prompt("Acción").lower()
        action = {"g": "push", "r": "pop"}.get(choice, "")

    if action == "push":
        if not has_changes():
            info("No hay cambios para guardar.")
            return True
        git("stash", "push", "-u")
        ok("Cambios guardados en el stash.")
    elif action == "pop":
        if not stashes:
            info("No hay nada que recuperar.")
            return True
        if confirm("¿Recuperar el último stash?", default=True):
            git("stash", "pop")
            ok("Cambios recuperados.")
    return True


def cmd_tag(args) -> bool:
    section("Etiquetas / versiones", "🏷")
    tags = git_out("tag", "--sort=-creatordate")
    if tags:
        print(bold("  Etiquetas existentes:"))
        for t in tags.splitlines()[:10]:
            print("    " + t)
        print()

    name = (getattr(args, "name", "") or "").strip() or (getattr(args, "message", "") or "").strip()
    if not name and not RT.assume_yes:
        name = prompt("Nombre de la etiqueta (ej. v1.0.0)")
    if not name:
        return True
    if not confirm(f"¿Crear la etiqueta '{name}'?", default=True):
        return False
    git("tag", "-a", name, "-m", name)
    ok(f"Etiqueta '{name}' creada.")
    if remote_url() and confirm("¿Subir la etiqueta al remoto?", default=True):
        try:
            net_git("push", "origin", name, msg="Subiendo etiqueta…")
            ok("Etiqueta subida.")
        except subprocess.CalledProcessError:
            err("No se pudo subir la etiqueta.")
    return True


def _parse_semver(tag: str) -> tuple[int, int, int]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", tag)
    if not m:
        return (0, 0, 0)
    return tuple(int(x) for x in m.groups())  # type: ignore[return-value]


def cmd_release(args) -> bool:
    box("🚀 Nueva versión (release)", [
        dim("  Calcula la versión desde tus commits y genera el CHANGELOG."),
    ])
    if not has_commits():
        info("Todavía no hay commits.")
        return True
    if has_changes():
        warn("Tienes cambios sin confirmar. Confírmalos antes de publicar una versión.")
        if not confirm("¿Continuar de todas formas?"):
            return False

    last_tag = git_out("describe", "--tags", "--abbrev=0")
    rng = f"{last_tag}..HEAD" if last_tag else "HEAD"
    subjects = [s for s in git_out("log", rng, "--pretty=%s").splitlines() if s]
    if not subjects:
        info("No hay commits nuevos desde la última versión.")
        return True

    feats, fixes, others, breaking = [], [], [], []
    for s in subjects:
        low = s.lower()
        if "!" in s.split(":")[0] or "breaking change" in low:
            breaking.append(s)
        if low.startswith("feat"):
            feats.append(s)
        elif low.startswith("fix"):
            fixes.append(s)
        else:
            others.append(s)

    major, minor, patch = _parse_semver(last_tag or "v0.0.0")
    if breaking:
        major, minor, patch = major + 1, 0, 0
    elif feats:
        minor, patch = minor + 1, 0
    else:
        patch += 1
    suggested = f"v{major}.{minor}.{patch}"

    section("Resumen de cambios", "📋")
    print(f"  {dim('Última versión:')} {last_tag or '(ninguna)'}")
    print(f"  {dim('Commits nuevos:')} {len(subjects)}   "
          f"{paint('✨ ' + str(len(feats)), C.GREEN)}  "
          f"{paint('🐛 ' + str(len(fixes)), C.YELLOW)}  "
          f"{dim('otros ' + str(len(others)))}")
    if breaking:
        warn(f"{len(breaking)} cambio(s) que rompen compatibilidad.")

    version = (getattr(args, "version", "") or "").strip()
    if not version and not RT.assume_yes:
        version = prompt("Versión a publicar", default=suggested)
    version = version or suggested

    date = datetime.now().strftime("%Y-%m-%d")
    entry = [f"## {version} ({date})", ""]
    if feats:
        entry.append("### ✨ Novedades")
        entry += [f"- {s}" for s in feats]
        entry.append("")
    if fixes:
        entry.append("### 🐛 Correcciones")
        entry += [f"- {s}" for s in fixes]
        entry.append("")
    if others:
        entry.append("### 🔧 Otros cambios")
        entry += [f"- {s}" for s in others]
        entry.append("")
    entry_text = "\n".join(entry) + "\n"

    print()
    print(dim("  Se añadirá al CHANGELOG.md:"))
    for line in entry[:12]:
        print("    " + line)
    if not confirm(f"¿Publicar la versión {bold(version)}?", default=True):
        info("Release cancelado.")
        return False

    changelog = repo_root() / "CHANGELOG.md"
    if RT.dry_run:
        info("[simulación] Actualizaría CHANGELOG.md y crearía el tag.")
    else:
        existing = changelog.read_text(encoding="utf-8") if changelog.exists() else "# Changelog\n"
        if not existing.startswith("# Changelog"):
            existing = "# Changelog\n" + existing
        # Insertar justo tras la primera línea (el encabezado), no tras el primer
        # doble salto: así la versión nueva queda siempre arriba (más reciente primero).
        head, _, rest = existing.partition("\n")
        rest = rest.lstrip("\n")
        changelog.write_text(head + "\n\n" + entry_text + "\n" + rest, encoding="utf-8")
        ok("CHANGELOG.md actualizado.")
    committed = create_commit(f"chore(release): {version}", silent=True)
    if not committed and not RT.dry_run:
        err("No se creó el commit del release (barrera de seguridad o sin cambios). Se aborta antes de crear la etiqueta.")
        return False
    git("tag", "-a", version, "-m", version)
    ok(f"Versión {version} creada.")
    if remote_url() and confirm("¿Subir versión y etiqueta al remoto?", default=True):
        try:
            net_git("push", "origin", current_branch(), msg="Subiendo commits…")
            net_git("push", "origin", version, msg="Subiendo etiqueta…")
            ok("Versión publicada. 🎉")
        except subprocess.CalledProcessError:
            err("No se pudo subir la versión.")
    return True


def _remote_web_url() -> str:
    """Convierte la URL del remoto en su URL web (github/gitlab)."""
    url = remote_url()
    if not url:
        return ""
    if url.startswith("git@"):
        host, _, path = url.partition("@")[2].partition(":")
    else:
        p = urlparse(url)
        host, path = p.hostname or "", p.path.lstrip("/")
    path = re.sub(r"\.git$", "", path)
    if not host or not path:
        return ""
    return f"https://{host}/{path}"


def cmd_pr(args) -> bool:
    section("Crear Pull Request", "🔀")
    branch = current_branch()
    if is_protected(branch):
        warn(f"Estás en la rama principal '{branch}'. Normalmente el PR se crea desde una rama de trabajo.")
    base = CONFIG.branch or "main"

    ahead, _ = ahead_behind()
    if ahead and confirm("Tienes commits sin subir. ¿Subirlos primero?", default=True):
        try:
            net_git("push", "-u", "origin", branch, msg="Subiendo cambios…")
        except subprocess.CalledProcessError:
            err("No se pudieron subir los cambios.")
            return False

    if shutil.which("gh"):
        info("Usando GitHub CLI (gh)…")
        try:
            run_git.__self__ if False else None  # no-op
            subprocess.run(["gh", "pr", "create", "--fill", "--base", base],
                           cwd=str(SCRIPT_DIR), check=True)
            ok("Pull Request creado.")
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            warn("No se pudo usar 'gh'. Abriré el navegador como alternativa.")

    web = _remote_web_url()
    if not web:
        err("No se pudo determinar la URL del repositorio.")
        return False
    pr_url = f"{web}/compare/{base}...{branch}?expand=1"
    print(f"  {dim('Abre esta URL para crear el PR:')}")
    print("  " + paint(pr_url, C.BRIGHT_CYAN, C.UNDER))
    if confirm("¿Abrir en el navegador?", default=True):
        try:
            webbrowser.open(pr_url)
        except Exception:
            pass
    return True


def cmd_undo(args) -> bool:
    section("Deshacer el último commit", "↩")
    if not has_commits():
        info("No hay commits que deshacer.")
        return True
    last = git_out("log", "-1", "--pretty=format:%h · %s")
    print(f"  {dim('Último commit:')} {bold(last)}")
    warn("Se deshará el commit pero se CONSERVARÁN tus cambios (git reset --soft).")
    if not confirm("¿Deshacer el último commit?"):
        info("Cancelado.")
        return False
    make_safety_snapshot("undo")
    git("reset", "--soft", "HEAD~1")
    ok("Commit deshecho. Tus cambios siguen en el área de trabajo.")
    return True


def cmd_discard(args) -> bool:
    section("Descartar cambios locales", "🗑")
    if not has_changes():
        info("No hay cambios locales que descartar.")
        return True
    modified, untracked, staged = changed_summary()
    err("¡ATENCIÓN! Esta operación es DESTRUCTIVA.")
    print(f"  Se perderán: {paint(str(modified + staged) + ' cambio(s)', C.YELLOW)}"
          f" y {paint(str(untracked) + ' archivo(s) nuevo(s)', C.CYAN)}.")
    info("Se creará una copia de seguridad por si acaso (usa 'rescue' para recuperar).")
    if not confirm("¿Seguro que quieres DESCARTAR todos los cambios locales?"):
        info("Cancelado. No se ha tocado nada.")
        return False
    if not confirm_phrase("DESCARTAR"):
        info("Cancelado.")
        return False
    make_safety_snapshot("discard")
    git("reset", "--hard", "HEAD")
    git("clean", "-fd", "-e", ".sync")  # nunca borrar la copia de seguridad recién creada
    ok("Cambios locales descartados (hay copia de seguridad, recupérala con 'rescue').")
    return True


def cmd_rescue(args) -> bool:
    section("Recuperar trabajo (reflog)", "🛟")
    if not has_commits():
        info("No hay historial que recuperar.")
        return True
    entries = []
    out = git_out("reflog", "--date=relative",
                  "--pretty=%h\x1f%gd\x1f%gs\x1f%cr")
    for line in out.splitlines()[:20]:
        parts = line.split("\x1f")
        if len(parts) == 4:
            entries.append(parts)
    if not entries:
        info("No hay entradas en el reflog.")
        return True
    rows = [[str(i), h, _clip(gs, 45), cr]
            for i, (h, gd, gs, cr) in enumerate(entries)]
    table(["#", "Hash", "Acción", "Cuándo"], rows)

    backups = [l for l in git_out(
        "for-each-ref", "--format=%(refname)", "refs/backups").splitlines() if l]
    if backups:
        print()
        info("Copias de cambios sin commitear (de 'discard'/'undo'). Para restaurar una:")
        for ref in backups[-5:]:
            print(dim(f"     git stash apply {ref}"))
    print()
    info("También hay bundles completos en .sync/backups/.")

    if RT.assume_yes:
        return True
    idx = prompt("Índice a recuperar (Enter para salir)")
    if not idx.isdigit() or int(idx) >= len(entries):
        return True
    target = entries[int(idx)][0]
    print(dim("  [v] ver en una rama nueva (seguro)   ·   [r] volver AQUÍ (reset --hard)"))
    mode = prompt("Modo", default="v")
    if mode.startswith("r"):
        warn("Esto moverá tu rama actual a ese punto y descartará lo posterior.")
        if not confirm_phrase("VOLVER"):
            return False
        make_safety_snapshot("rescue-reset")
        git("reset", "--hard", target)
        ok(f"Rama movida a {target}.")
    else:
        newb = f"rescate-{target}"
        git("switch", "-c", newb, target)
        ok(f"Creada la rama '{newb}' en {target} para inspeccionar sin riesgo.")
    return True


def cmd_restore(args) -> bool:
    section("Restaurar un archivo", "♻")
    path = (getattr(args, "path", "") or "").strip()
    if not path:
        changed = [l[3:] for l in git_out("status", "--porcelain").splitlines() if l]
        if not changed:
            info("No hay archivos modificados que restaurar.")
            return True
        rows = [[str(i), c] for i, c in enumerate(changed)]
        table(["#", "Archivo"], rows)
        sel = prompt("Número o ruta del archivo")
        if sel.isdigit() and int(sel) < len(changed):
            path = changed[int(sel)]
        else:
            path = sel
    if not path:
        return True

    source = (getattr(args, "source", "") or "").strip()
    warn(f"Se perderán los cambios actuales de '{path}'.")
    if not confirm("¿Continuar?"):
        return False
    if source:
        git("restore", "--source", source, "--", path)
    else:
        git("restore", "--", path)
    ok(f"'{path}' restaurado.")
    return True


def cmd_clone(args) -> bool:
    section("Clonar repositorio", "📥")
    url = (getattr(args, "url", "") or "").strip()
    if not url:
        url = prompt("URL del repositorio a clonar")
    if not url:
        err("Necesitas una URL para clonar.")
        return False
    dest = (getattr(args, "dest", "") or "").strip()
    print(f"  {dim('Origen:')} {bold(url)}")
    if dest:
        print(f"  {dim('Destino:')} {dest}")
    if not confirm("¿Clonar ahora?", default=True):
        return False
    cmd = ["clone", url] + ([dest] if dest else [])
    try:
        with Spinner("Clonando…"):
            run_git(*cmd, cwd=SCRIPT_DIR, capture=True)
    except subprocess.CalledProcessError as exc:
        explain_git_error(exc.stderr or "")
        err("No se pudo clonar el repositorio.")
        return False
    ok("Repositorio clonado correctamente.")
    return True


def cmd_remote(args) -> bool:
    section("Gestión de remotos", "🔗")
    remotes = git_out("remote", "-v")
    if remotes:
        print(bold("  Remotos configurados:"))
        for line in remotes.splitlines():
            print("    " + dim(line))
    else:
        info("No hay remotos configurados.")
    print()

    new_url = (getattr(args, "url", "") or "").strip()
    if not new_url and not RT.assume_yes:
        new_url = prompt("Nueva URL para 'origin' (Enter para salir)")
    if not new_url:
        return True
    if remote_url():
        if confirm(f"¿Cambiar 'origin' a '{new_url}'?", default=True):
            git("remote", "set-url", "origin", new_url)
    else:
        git("remote", "add", "origin", new_url)
    CONFIG.remote = new_url
    save_config(CONFIG)
    ok(f"Remoto 'origin' → {bold(new_url)}")
    return True


PROJECT_SIGNATURES = {
    "Python": ["requirements.txt", "pyproject.toml", "setup.py", "Pipfile"],
    "Node": ["package.json"],
    "Java": ["pom.xml", "build.gradle"],
    "Rust": ["Cargo.toml"],
    "Go": ["go.mod"],
    ".NET": ["*.csproj", "*.sln"],
}


def detect_project_types() -> list[str]:
    root = repo_root()
    found = []
    for kind, sigs in PROJECT_SIGNATURES.items():
        for sig in sigs:
            if list(root.glob(sig)):
                found.append(kind)
                break
    return found


def cmd_ignore(args) -> bool:
    section("Archivo .gitignore", "📄")
    kinds = detect_project_types()
    if kinds:
        info(f"Tipos de proyecto detectados: {', '.join(kinds)}")
    gitignore = SCRIPT_DIR / ".gitignore"
    if gitignore.exists():
        info(f".gitignore ya existe ({len(gitignore.read_text(encoding='utf-8').splitlines())} líneas).")
        if not confirm("¿Añadir las reglas recomendadas al final?", default=False):
            return True
        _write_gitignore(append=True, kinds=kinds)
    else:
        _write_gitignore(kinds=kinds)
    return True


_IGNORE_BASE = """# --- G-Sync ---
.sync/
.DS_Store
Thumbs.db
desktop.ini
.vscode/
.idea/
*.swp
.env
.env.*
*.local
*.log
"""

_IGNORE_BY_KIND = {
    "Python": "__pycache__/\n*.py[cod]\n*.egg-info/\n.venv/\nvenv/\nenv/\n.pytest_cache/\n.mypy_cache/\n",
    "Node": "node_modules/\ndist/\nbuild/\n.next/\ncoverage/\n",
    "Java": "target/\n*.class\n.gradle/\n",
    "Rust": "target/\nCargo.lock\n",
    "Go": "bin/\n",
    ".NET": "bin/\nobj/\n",
}


def _write_gitignore(append: bool = False, kinds: list[str] | None = None) -> None:
    kinds = kinds or detect_project_types()
    content = _IGNORE_BASE
    for kind in kinds:
        content += f"\n# {kind}\n" + _IGNORE_BY_KIND.get(kind, "")
    gitignore = SCRIPT_DIR / ".gitignore"
    if RT.dry_run:
        info("[simulación] Escribiría .gitignore")
        return
    if append and gitignore.exists():
        existing = gitignore.read_text(encoding="utf-8")
        new_lines = [l for l in content.splitlines() if l and l not in existing.splitlines()]
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n" + "\n".join(new_lines) + "\n")
        ok(f"{len(new_lines)} regla(s) añadida(s) a .gitignore.")
    else:
        gitignore.write_text(content, encoding="utf-8")
        ok(".gitignore creado.")


def cmd_hooks(args) -> bool:
    section("Git hooks", "🪝")
    action = (getattr(args, "action", "") or "").strip()
    hooks_dir = repo_root() / ".git" / "hooks"
    if not hooks_dir.parent.exists():
        err("No es un repositorio Git.")
        return False
    if not action and not RT.assume_yes:
        print(dim("  [i] instalar   ·   [q] quitar   ·   [Enter] salir"))
        action = {"i": "install", "q": "remove"}.get(prompt("Acción").lower(), "")

    python = sys.executable or "python"
    script = str(SCRIPT_DIR / "sync.py")
    pre_commit = hooks_dir / "pre-commit"
    if action == "install":
        content = ("#!/bin/sh\n"
                   f'"{python}" "{script}" hookcheck || exit 1\n')
        if RT.dry_run:
            info("[simulación] Instalaría el hook pre-commit.")
            return True
        # Forzar LF: un shebang con CRLF puede romper el intérprete del hook.
        with pre_commit.open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)
        try:
            os.chmod(pre_commit, 0o755)
        except OSError:
            pass
        ok("Hook 'pre-commit' instalado (valida secretos y archivos grandes).")
    elif action == "remove":
        if pre_commit.exists() and not RT.dry_run:
            pre_commit.unlink()
        ok("Hook 'pre-commit' eliminado.")
    else:
        info("Sin cambios.")
    return True


def cmd_hookcheck(_args) -> bool:
    """Comando invocado por el hook pre-commit. Devuelve False si hay problemas
    (main() lo traduce a código de salida 1, que el hook usa con '|| exit 1')."""
    prev_quiet = RT.quiet
    RT.quiet = True
    try:
        paths = _staged_files()
        if not paths:
            return True
        _, blocks = check_large_files(paths)
        findings = scan_secrets(paths) if CONFIG.secret_scan else []
        if blocks or findings:
            RT.quiet = False
            err("El commit fue bloqueado por G-Sync:")
            for p, s in blocks:
                print(f"     Archivo enorme: {p} ({human_size(s)})")
            for f, t, m in findings:
                print(f"     Posible secreto: {f} · {t}")
            return False
        return True
    finally:
        RT.quiet = prev_quiet


def cmd_watch(args) -> bool:
    interval = int(getattr(args, "interval", 0) or CONFIG.watch_interval or 300)
    debounce = CONFIG.watch_debounce
    box("👁  Modo automático (watch)", [
        dim(f"  Vigila cambios y sincroniza tras {debounce}s de calma, cada {interval}s máx."),
        dim("  Reintentos automáticos ante fallos de red. Ctrl+C para detener."),
    ], color=C.BRIGHT_MAGENTA)
    if not ensure_remote():
        return False
    if not confirm("¿Iniciar la sincronización automática?", default=True):
        return False

    branch = current_branch()
    saved_confirm, saved_yes = CONFIG.confirm, RT.assume_yes
    CONFIG.confirm, RT.assume_yes, RT.quiet = False, True, True
    started = time.time()
    count = errors = 0
    last_change_hash = ""
    last_change_time = 0.0
    last_commit_time = 0.0
    retry_delay = 5
    try:
        while True:
            now = time.time()
            cur_hash = git_out("status", "--porcelain")
            if cur_hash and cur_hash != last_change_hash:
                last_change_hash = cur_hash
                last_change_time = now
            quiet_enough = last_change_time and (now - last_change_time) >= debounce
            interval_ok = (now - last_commit_time) >= interval
            if cur_hash and quiet_enough and interval_ok:
                ts = datetime.now().strftime("%H:%M:%S")
                msg = commit_message()
                print(paint(f"\n[{ts}] ", C.GREY) + paint("Sincronizando…", C.CYAN))
                create_commit(msg, silent=True)
                try:
                    net_git("pull", "--rebase", "origin", branch, msg="pull", attempts=2)
                    net_git("push", "-u", "origin", branch, msg="push", attempts=3)
                    count += 1
                    last_commit_time = now
                    last_change_hash = ""
                    retry_delay = 5
                    ok(f"Sincronización #{count} completada.")
                    audit(f"watch sync #{count} ({msg})")
                except subprocess.CalledProcessError:
                    errors += 1
                    warn(f"Fallo de sincronización; reintento en {retry_delay}s.")
                    audit(f"watch error #{errors}")
                    time.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 300)
                    continue
            time.sleep(min(5, interval))
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        CONFIG.confirm, RT.assume_yes, RT.quiet = saved_confirm, saved_yes, False
        print()
        box("Resumen de la sesión watch", [
            f"  {dim('Duración      ')} {fmt_duration(time.time() - started)}",
            f"  {dim('Sincronizaciones')} {count}",
            f"  {dim('Errores       ')} {errors}",
        ], color=C.BRIGHT_MAGENTA)
    return True


def cmd_schedule(args) -> bool:
    section("Sincronización programada", "⏰")
    action = (getattr(args, "action", "") or "").strip()
    minutes = int(getattr(args, "interval", 0) or 30)
    task_name = f"G-Sync-{SCRIPT_DIR.name}"
    python = sys.executable or "python"
    pythonw = python.replace("python.exe", "pythonw.exe")
    if os.name == "nt" and Path(pythonw).exists():
        python = pythonw
    script = str(SCRIPT_DIR / "sync.py")

    if not action and not RT.assume_yes:
        print(dim("  [i] instalar   ·   [q] quitar   ·   [e] estado   ·   [Enter] salir"))
        action = {"i": "install", "q": "remove", "e": "status"}.get(prompt("Acción").lower(), "")

    is_windows = os.name == "nt"
    if action == "install":
        if not RT.assume_yes:
            minutes = int(prompt("¿Cada cuántos minutos?", default=str(minutes)) or minutes)
        if is_windows:
            cmd = ["schtasks", "/Create", "/SC", "MINUTE", "/MO", str(minutes),
                   "/TN", task_name, "/TR", f'"{python}" "{script}" save -y -q', "/F"]
        else:
            cron_line = f'*/{minutes} * * * * cd "{SCRIPT_DIR}" && "{python}" "{script}" save -y -q  # {task_name}'
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            existing = "\n".join(l for l in existing.splitlines() if task_name not in l)
            new_cron = (existing + "\n" + cron_line + "\n").strip() + "\n"
            if RT.dry_run:
                info(f"[simulación] Añadiría al cron:\n     {cron_line}")
                return True
            subprocess.run(["crontab", "-"], input=new_cron, text=True)
            ok(f"Tarea cron instalada (cada {minutes} min).")
            return True
        if RT.dry_run:
            info(f"[simulación] {' '.join(cmd)}")
            return True
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            ok(f"Tarea programada '{task_name}' creada (cada {minutes} min).")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            err(f"No se pudo crear la tarea programada: {exc}")
            return False
    elif action == "remove":
        if is_windows:
            subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"],
                           capture_output=True, text=True)
        else:
            existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
            new_cron = "\n".join(l for l in existing.splitlines() if task_name not in l) + "\n"
            subprocess.run(["crontab", "-"], input=new_cron, text=True)
        ok("Programación eliminada.")
    elif action == "status":
        if is_windows:
            res = subprocess.run(["schtasks", "/Query", "/TN", task_name],
                                 capture_output=True, text=True)
            print(res.stdout or dim("  No hay ninguna tarea programada."))
        else:
            res = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            lines = [l for l in res.stdout.splitlines() if task_name in l]
            print("\n".join("  " + l for l in lines) if lines
                  else dim("  No hay ninguna tarea cron."))
    else:
        info("Sin cambios.")
    return True


def cmd_history(args) -> bool:
    section("Registro de auditoría", "📜")
    path = _audit_log_path()
    if not path.exists():
        info("Todavía no hay registro de sincronizaciones automáticas.")
        return True
    n = int(getattr(args, "count", 20) or 20)
    with path.open(encoding="utf-8") as f:
        last = deque(f, maxlen=n)
    for line in last:
        line = line.rstrip()
        if "error" in line.lower():
            print("  " + paint(line, C.RED))
        else:
            print("  " + dim(line))
    return True


def cmd_protect(args) -> bool:
    section("Protección de ramas", "🛡")
    print(f"  {dim('Ramas protegidas:')} {', '.join(CONFIG.protected_branches) or '(ninguna)'}")
    print(f"  {dim('Bloquear push directo:')} {'sí' if CONFIG.block_direct_push else 'no'}")
    if RT.assume_yes:
        return True
    print()
    print(dim("  [a] añadir rama   ·   [r] quitar rama   ·   [b] alternar bloqueo   ·   [Enter] salir"))
    choice = prompt("Acción").lower()
    if choice == "a":
        name = prompt("Rama o patrón a proteger (ej. release/*)")
        if name and name not in CONFIG.protected_branches:
            CONFIG.protected_branches.append(name)
            save_config(CONFIG)
            ok(f"'{name}' añadida a ramas protegidas.")
    elif choice == "r":
        name = prompt("Rama a quitar")
        if name in CONFIG.protected_branches:
            CONFIG.protected_branches.remove(name)
            save_config(CONFIG)
            ok(f"'{name}' quitada.")
    elif choice == "b":
        CONFIG.block_direct_push = not CONFIG.block_direct_push
        save_config(CONFIG)
        ok(f"Bloqueo de push directo: {'activado' if CONFIG.block_direct_push else 'desactivado'}.")
    return True


def cmd_archive(args) -> bool:
    section("Exportar snapshot (.zip)", "🗜")
    if not has_commits():
        info("No hay commits que exportar.")
        return True
    name = (getattr(args, "output", "") or "").strip()
    if not name:
        name = f"{SCRIPT_DIR.name}-{datetime.now():%Y%m%d}.zip"
    out = Path(name)
    if not out.is_absolute():
        out = SCRIPT_DIR.parent / name
    print(f"  {dim('Destino:')} {out}")
    if not confirm("¿Exportar el proyecto (sin .git) a un .zip?", default=True):
        return False
    if RT.dry_run:
        info("[simulación] Crearía el archivo .zip.")
        return True
    try:
        run_git("archive", "--format=zip", "-o", str(out), "HEAD", capture=True)
        size = out.stat().st_size
        ok(f"Snapshot creado: {out.name} ({human_size(size)})")
    except subprocess.CalledProcessError:
        err("No se pudo crear el archivo.")
        return False
    return True


def cmd_config(args) -> bool:
    if getattr(args, "export_path", ""):
        return _config_export(args.export_path)
    if getattr(args, "import_path", ""):
        return _config_import(args.import_path)

    glob = getattr(args, "global_conf", False)
    box("🔧 Configuración " + ("global" if glob else "del proyecto"), [
        f"  {dim('Archivo:')} {GLOBAL_CONFIG if glob else CONFIG_FILE}",
    ])
    if CONFIG_WARNINGS:
        print()
        for w in CONFIG_WARNINGS:
            warn(w)
    print()
    print(bold("  Valores actuales:"))
    print(f"    Remoto           : {configured_remote() or dim('(ninguno)')}")
    print(f"    Rama             : {CONFIG.branch or current_branch()}")
    print(f"    Estrategia pull  : {CONFIG.pull_strategy}")
    print(f"    Estilo de commit : {CONFIG.commit_style}")
    print(f"    Auto-stash       : {'sí' if CONFIG.auto_stash else 'no'}")
    print(f"    Confirmaciones   : {CONFIG.confirm_level}")
    print(f"    Escáner secretos : {'sí' if CONFIG.secret_scan else 'no'}")
    print(f"    Plantilla commit : {CONFIG.commit_template}")
    print(f"    Intervalo watch  : {CONFIG.watch_interval}s")
    print(f"    Ramas protegidas : {', '.join(CONFIG.protected_branches)}")

    if RT.assume_yes:
        return True
    print()
    print(dim("  Pulsa Enter para conservar cada valor."))
    try:
        new_remote = prompt("URL del repositorio", default=configured_remote())
        new_branch = prompt("Rama principal", default=CONFIG.branch or current_branch())
        new_strategy = prompt("Estrategia pull (rebase/merge)", default=CONFIG.pull_strategy)
        new_style = prompt("Estilo commit (libre/conventional)", default=CONFIG.commit_style)
        new_stash = prompt("Auto-stash (s/n)", default="s" if CONFIG.auto_stash else "n")
        new_secret = prompt("Escáner de secretos (s/n)", default="s" if CONFIG.secret_scan else "n")
        new_confirm = prompt("Confirmaciones (smart/always/never)", default=CONFIG.confirm_level)
        new_template = prompt("Plantilla de commit", default=CONFIG.commit_template)
        new_interval = prompt("Intervalo watch (segundos)", default=str(CONFIG.watch_interval))
    except (KeyboardInterrupt, EOFError):
        print()
        info("Configuración cancelada.")
        return False

    if new_remote and new_remote != remote_url():
        if is_git_repo() and not glob:
            if remote_url():
                if confirm("¿Actualizar también el remoto 'origin' en Git?", default=True):
                    git("remote", "set-url", "origin", new_remote)
            else:
                git("remote", "add", "origin", new_remote)
        CONFIG.remote = new_remote
    CONFIG.branch = new_branch or CONFIG.branch
    CONFIG.pull_strategy = "merge" if new_strategy.lower().startswith("m") else "rebase"
    CONFIG.commit_style = "conventional" if new_style.lower().startswith("c") else "libre"
    CONFIG.auto_stash = new_stash.lower().startswith("s")
    CONFIG.secret_scan = new_secret.lower().startswith("s")
    if new_confirm in ("smart", "always", "never"):
        CONFIG.confirm_level = new_confirm
        CONFIG.confirm = new_confirm != "never"
    CONFIG.commit_template = new_template or CONFIG.commit_template
    try:
        CONFIG.watch_interval = max(10, int(new_interval))
    except ValueError:
        pass
    save_config(CONFIG, glob=glob)
    ok("Configuración guardada.")
    return True


def _config_export(path: str) -> bool:
    section("Exportar configuración", "📤")
    data = asdict(CONFIG)
    data.pop("remote", None)  # nunca exportar posibles credenciales embebidas
    out = Path(path)
    if RT.dry_run:
        info(f"[simulación] Exportaría a {out}")
        return True
    out.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    ok(f"Configuración exportada a {out} (sin la URL del remoto).")
    return True


def _config_import(path: str) -> bool:
    section("Importar configuración", "📥")
    src = Path(path)
    if not src.exists():
        err(f"No existe el archivo: {src}")
        return False
    data = _read_json(src)
    applied = 0
    for k, v in data.items():
        if k in _VALID_KEYS and k != "remote":
            setattr(CONFIG, k, v)
            applied += 1
    _validate_config(CONFIG)
    save_config(CONFIG)
    ok(f"Importadas {applied} clave(s) de configuración.")
    return True


def cmd_doctor(args) -> bool:
    box("🩺 Diagnóstico", [dim("  Comprobando el entorno de trabajo…")])
    problems = 0
    fix = getattr(args, "fix", False)

    section("Git", "")
    if git_available():
        ok(f"Git instalado: {git_out('--version')}")
    else:
        err("Git no está instalado o no está en el PATH.")
        return False
    if is_git_repo():
        ok("Este directorio es un repositorio Git.")
    else:
        err("Este directorio todavía NO es un repositorio Git (usa 'setup').")
        return False

    section("Identidad", "")
    name, email = git_out("config", "user.name"), git_out("config", "user.email")
    if name and email:
        ok(f"Configurado como: {name} <{email}>")
    else:
        warn("Falta configurar tu identidad de Git (usa 'setup').")
        problems += 1

    section("Windows / seguridad", "")
    if os.name == "nt":
        autocrlf = git_out("config", "core.autocrlf")
        if autocrlf:
            ok(f"core.autocrlf = {autocrlf}")
        else:
            warn("core.autocrlf sin configurar (recomendado 'true' en Windows).")
            if fix and not RT.dry_run:
                git("config", "--global", "core.autocrlf", "true")
                ok("Corregido: core.autocrlf = true")
            else:
                problems += 1
    helper = git_out("config", "credential.helper")
    if helper:
        ok(f"credential.helper = {helper}")
    else:
        info("Sin credential.helper (Git pedirá credenciales cada vez).")

    section("Secretos ya versionados", "")
    tracked = [f for f in git_out("ls-files").splitlines() if _SENSITIVE_NAMES.search(f)]
    if tracked:
        warn("Archivos sensibles ya versionados:")
        for f in tracked:
            print(f"     {paint(f, C.RED)}")
        problems += 1
    else:
        ok("No hay archivos sensibles versionados.")

    section("Remoto", "")
    remote = remote_url()
    if remote:
        ok(f"origin → {remote}")
        with Spinner("Comprobando acceso al remoto…"):
            res = run_git("ls-remote", "--heads", "origin", check=False, capture=True)
        if res.returncode == 0:
            ok("El remoto responde correctamente.")
        else:
            warn("No se pudo acceder al remoto. Revisa credenciales (token/SSH).")
            problems += 1
    else:
        warn("No existe el remoto 'origin'.")
        problems += 1

    section("Estado", "")
    ok(f"Rama actual: {current_branch()}")
    if git_out("symbolic-ref", "-q", "HEAD") == "":
        warn("Estás en 'detached HEAD'.")
        problems += 1

    if CONFIG_WARNINGS:
        section("Configuración", "")
        for w in CONFIG_WARNINGS:
            warn(w)

    print()
    if problems:
        warn(f"Diagnóstico terminado con {problems} aviso(s).")
        if not fix:
            info("Prueba 'python sync.py doctor --fix' para corregir los automáticos.")
    else:
        box("✔ Todo correcto", [paint("  No se detectaron problemas.", C.BRIGHT_GREEN)],
            color=C.BRIGHT_GREEN)
    return problems == 0


def cmd_selftest(_args) -> bool:
    box("🧪 Auto-tests de G-Sync", [dim("  Verificando integridad interna…")])
    passed = failed = 0

    def check(desc: str, cond: bool) -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            ok(desc)
        else:
            failed += 1
            err(desc)

    names = [c.name for c in REGISTRY]
    check("Nombres de comando únicos", len(names) == len(set(names)))

    all_aliases = [a for c in REGISTRY for a in c.aliases]
    check("Alias sin colisión con nombres", not (set(all_aliases) & set(names)))
    check("Alias únicos entre sí", len(all_aliases) == len(set(all_aliases)))

    try:
        parser = build_parser()
        ns = parser.parse_args(["st"])
        check("El alias 'st' resuelve a status", getattr(ns, "_cmd", "") == "status")
    except SystemExit:
        check("El alias 'st' resuelve a status", False)

    check("Todo comando de menú tiene grupo", all(c.group for c in REGISTRY if c.name in MENU_ORDER))
    check("Cada comando tiene función", all(callable(c.func) for c in REGISTRY))
    check("Medición de ancho con emoji", _visible_len("🔒") == 2 and _visible_len("ab") == 2)
    check("Bloques de sparkline ancho 1", _visible_len("▁▂▃") == 3)

    print()
    if failed == 0:
        box("✔ Todos los tests pasaron", [paint(f"  {passed} comprobaciones OK.", C.BRIGHT_GREEN)],
            color=C.BRIGHT_GREEN)
    else:
        warn(f"{failed} test(s) fallaron, {passed} pasaron.")
    return failed == 0


def _print_rebase_help() -> None:
    print()
    print(bold("  ¿Conflicto? Sigue estos pasos:"))
    print(dim("    1. Edita los archivos en conflicto y guarda."))
    print(dim("    2. git add <archivos>"))
    print(dim("    3. git rebase --continue"))
    print(dim("  Para cancelar todo el proceso:  git rebase --abort"))


# =============================================================================
# 10 · REGISTRO ÚNICO DE COMANDOS (fuente de verdad para menú + CLI)
# =============================================================================

@dataclass(frozen=True)
class Arg:
    flags: tuple
    kw: dict


@dataclass(frozen=True)
class Cmd:
    name: str
    func: Callable
    group: str = ""            # "" → no aparece en el menú
    icon: str = ""
    help: str = ""
    aliases: tuple = ()
    needs_repo: bool = True
    msg_prompt: str = ""       # si se define, el menú pide un texto
    msg_required: bool = False
    args: tuple = ()


G_DAILY = "Trabajo diario"
G_INSPECT = "Inspeccionar"
G_BRANCH = "Ramas y publicación"
G_RECOVER = "Recuperación"
G_AUTO = "Automatización"
G_CONFIG = "Configuración"

REGISTRY: list[Cmd] = [
    # Trabajo diario ----------------------------------------------------------
    Cmd("status", cmd_status, G_DAILY, "📊", "Estado detallado del repositorio.", ("st", "s")),
    Cmd("sync", cmd_sync, G_DAILY, "🔄", "Todo en uno: commit + rebase + push.", ("sy",),
        msg_prompt="Mensaje del commit (Enter = automático)",
        args=(Arg(("-m", "--message"), {"default": "", "help": "Mensaje del commit."}),)),
    Cmd("save", cmd_save, G_DAILY, "💾", "Guardado rápido (commit auto + push).",
        msg_prompt="Mensaje del commit (Enter = automático)",
        args=(Arg(("-m", "--message"), {"default": "", "help": "Mensaje opcional."}),)),
    Cmd("push", cmd_push, G_DAILY, "⬆", "add + commit + push.", ("ps", "up"),
        msg_prompt="Mensaje del commit (Enter = automático)",
        args=(Arg(("-m", "--message"), {"default": "", "help": "Mensaje del commit."}),
              Arg(("--force-protected",), {"action": "store_true", "help": "Permite push a rama protegida."}))),
    Cmd("pull", cmd_pull, G_DAILY, "⬇", "Trae cambios del remoto.", ("pl",)),
    Cmd("commit", cmd_commit, G_DAILY, "📝", "Crea un commit (sin subir).", ("ci",),
        msg_prompt="Mensaje del commit", msg_required=True,
        args=(Arg(("-m", "--message"), {"default": "", "help": "Mensaje del commit."}),
              Arg(("--guided",), {"action": "store_true", "help": "Asistente Conventional Commits."}))),
    Cmd("amend", cmd_amend, G_DAILY, "✏", "Corrige el último commit.",
        args=(Arg(("-m", "--message"), {"default": "", "help": "Nuevo mensaje."}),)),
    # Inspeccionar ------------------------------------------------------------
    Cmd("dashboard", cmd_dashboard, G_INSPECT, "🖥", "Panel de estado (--watch para vivo).", ("panel",),
        args=(Arg(("--watch",), {"action": "store_true", "help": "Actualización en vivo."}),)),
    Cmd("log", cmd_log, G_INSPECT, "🕑", "Historial de commits.", ("lg",),
        args=(Arg(("-c", "--count"), {"type": int, "default": 15, "help": "Nº de commits."}),)),
    Cmd("diff", cmd_diff, G_INSPECT, "🔍", "Cambios pendientes.", ("df",),
        args=(Arg(("--full",), {"action": "store_true", "help": "Diferencias línea a línea."}),)),
    Cmd("find", cmd_find, G_INSPECT, "🔎", "Busca en el historial.",
        args=(Arg(("term",), {"nargs": "?", "default": "", "help": "Texto a buscar."}),
              Arg(("--mode",), {"default": "", "help": "m (mensaje) o c (código)."}))),
    Cmd("who", cmd_who, G_INSPECT, "👥", "Contribuidores y actividad."),
    # Ramas y publicación -----------------------------------------------------
    Cmd("branch", cmd_branch, G_BRANCH, "🌿", "Lista, crea o cambia de rama.", ("br",),
        args=(Arg(("name",), {"nargs": "?", "default": "", "help": "Rama a crear/cambiar."}),)),
    Cmd("stash", cmd_stash, G_BRANCH, "📦", "Guarda o recupera cambios temporales.",
        args=(Arg(("action",), {"nargs": "?", "default": "", "choices": ["", "push", "pop"], "help": "push/pop."}),)),
    Cmd("tag", cmd_tag, G_BRANCH, "🏷", "Crea una etiqueta/versión.",
        msg_prompt="Nombre de la etiqueta (ej. v1.0.0)",
        args=(Arg(("name",), {"nargs": "?", "default": "", "help": "Nombre de la etiqueta."}),
              Arg(("-m", "--message"), {"default": "", "help": "Nombre de la etiqueta."}))),
    Cmd("release", cmd_release, G_BRANCH, "🚀", "Sube versión semántica + CHANGELOG.",
        args=(Arg(("version",), {"nargs": "?", "default": "", "help": "Versión (ej. v1.2.0)."}),)),
    Cmd("pr", cmd_pr, G_BRANCH, "🔀", "Crea un Pull Request (gh o navegador)."),
    # Recuperación ------------------------------------------------------------
    Cmd("undo", cmd_undo, G_RECOVER, "↩", "Deshace el último commit (conserva cambios)."),
    Cmd("discard", cmd_discard, G_RECOVER, "🗑", "Descarta cambios locales (con backup)."),
    Cmd("rescue", cmd_rescue, G_RECOVER, "🛟", "Recupera trabajo perdido (reflog)."),
    Cmd("restore", cmd_restore, G_RECOVER, "♻", "Restaura UN archivo a versión previa.",
        args=(Arg(("path",), {"nargs": "?", "default": "", "help": "Archivo a restaurar."}),
              Arg(("--source",), {"default": "", "help": "Commit/hash de origen."}))),
    # Automatización ----------------------------------------------------------
    Cmd("watch", cmd_watch, G_AUTO, "👁", "Modo automático inteligente.",
        args=(Arg(("-i", "--interval"), {"type": int, "default": 0, "help": "Segundos entre ciclos."}),)),
    Cmd("schedule", cmd_schedule, G_AUTO, "⏰", "Programa la sincronización en el SO.",
        args=(Arg(("action",), {"nargs": "?", "default": "", "choices": ["", "install", "remove", "status"], "help": ""}),
              Arg(("-i", "--interval"), {"type": int, "default": 0, "help": "Minutos."}))),
    Cmd("hooks", cmd_hooks, G_AUTO, "🪝", "Instala/quita git hooks.",
        args=(Arg(("action",), {"nargs": "?", "default": "", "choices": ["", "install", "remove"], "help": ""}),)),
    Cmd("history", cmd_history, G_AUTO, "📜", "Registro de sincronizaciones automáticas.",
        needs_repo=False,
        args=(Arg(("-c", "--count"), {"type": int, "default": 20, "help": "Nº de líneas."}),)),
    # Configuración -----------------------------------------------------------
    Cmd("setup", cmd_setup, G_CONFIG, "⚙", "Asistente de configuración.", needs_repo=False,
        args=(Arg(("--url",), {"default": "", "help": "URL del repositorio."}),
              Arg(("--branch",), {"default": "", "help": "Rama principal."}))),
    Cmd("config", cmd_config, G_CONFIG, "🔧", "Configuración (global, export/import).", needs_repo=False,
        args=(Arg(("--global",), {"action": "store_true", "dest": "global_conf", "help": "Editar config global."}),
              Arg(("--export",), {"default": "", "dest": "export_path", "help": "Exportar a un archivo."}),
              Arg(("--import",), {"default": "", "dest": "import_path", "help": "Importar de un archivo."}))),
    Cmd("protect", cmd_protect, G_CONFIG, "🛡", "Reglas de protección de ramas."),
    Cmd("ignore", cmd_ignore, G_CONFIG, "📄", "Crea/actualiza el .gitignore."),
    Cmd("remote", cmd_remote, G_CONFIG, "🔗", "Gestiona los remotos.",
        args=(Arg(("--url",), {"default": "", "help": "Nueva URL para origin."}),)),
    Cmd("clone", cmd_clone, G_CONFIG, "📥", "Clona un repositorio.", needs_repo=False,
        args=(Arg(("url",), {"nargs": "?", "default": "", "help": "URL del repositorio."}),
              Arg(("dest",), {"nargs": "?", "default": "", "help": "Carpeta destino."}))),
    Cmd("archive", cmd_archive, G_CONFIG, "🗜", "Exporta un .zip del proyecto.",
        args=(Arg(("output",), {"nargs": "?", "default": "", "help": "Archivo .zip destino."}),)),
    Cmd("doctor", cmd_doctor, G_CONFIG, "🩺", "Diagnóstico del entorno.", needs_repo=False,
        args=(Arg(("--fix",), {"action": "store_true", "help": "Corrige lo automático."}),)),
    Cmd("selftest", cmd_selftest, G_CONFIG, "🧪", "Auto-tests internos.", needs_repo=False),
    # Ocultos (sin grupo) -----------------------------------------------------
    Cmd("hookcheck", cmd_hookcheck, "", needs_repo=True),
]

BY_NAME: dict[str, Cmd] = {c.name: c for c in REGISTRY}
BY_ALIAS: dict[str, Cmd] = {a: c for c in REGISTRY for a in c.aliases}
GROUPS_ORDER = [G_DAILY, G_INSPECT, G_BRANCH, G_RECOVER, G_AUTO, G_CONFIG]
MENU_ORDER = [c.name for c in REGISTRY if c.group]


def resolve(name: str) -> Cmd | None:
    return BY_NAME.get(name) or BY_ALIAS.get(name)


# =============================================================================
# 11 · MENÚ INTERACTIVO
# =============================================================================

LOGO = r"""   ____   ____
  / ___| / ___| _   _ _ __   ___
 | |  _  \___ \| | | | '_ \ / __|
 | |_| |  ___) | |_| | | | | (__
  \____| |____/ \__, |_| |_|\___|
                |___/            """


def print_header() -> None:
    branch = current_branch() if is_git_repo() else (CONFIG.branch or "main")
    remote = configured_remote()
    width = ui_width()

    print()
    if width >= 60 and RT.color:
        for line in LOGO.splitlines():
            print(paint(line, C.BRIGHT_CYAN))
        print(dim(f"  Gestor de sincronización Git · v{APP_VERSION}"))
    else:
        box(f"{APP_NAME} · Git · v{APP_VERSION}", [])

    print()
    print(f"  {dim('Proyecto')}  {bold(SCRIPT_DIR.name)}")
    print(f"  {dim('Rama')}      {branch}" +
          (paint("  🔒", C.YELLOW) if is_protected(branch) else ""))
    print(f"  {dim('Remoto')}    {remote or paint('(sin configurar — usa Configuración › setup)', C.YELLOW)}")

    if is_git_repo():
        modified, untracked, staged = changed_summary()
        if modified + untracked + staged:
            bits = []
            if staged:
                bits.append(paint(f"{staged} preparado(s)", C.GREEN))
            if modified:
                bits.append(paint(f"{modified} modificado(s)", C.YELLOW))
            if untracked:
                bits.append(paint(f"{untracked} nuevo(s)", C.CYAN))
            print(f"  {dim('Cambios')}   " + dim(" · ").join(bits))
        else:
            print(f"  {dim('Cambios')}   " + paint("árbol limpio ✔", C.GREEN))
        if remote_url():
            ahead, behind = ahead_behind()
            sync_bits = []
            if ahead:
                sync_bits.append(paint(f"↑{ahead}", C.YELLOW))
            if behind:
                sync_bits.append(paint(f"↓{behind}", C.CYAN))
            if sync_bits:
                print(f"  {dim('Remoto ⇅')}  " + " ".join(sync_bits))


def interactive_menu() -> None:
    while True:
        print_header()
        numbered: list[Cmd] = []
        n = 1
        for group in GROUPS_ORDER:
            cmds = [c for c in REGISTRY if c.group == group]
            if not cmds:
                continue
            section(group)
            for c in cmds:
                numbered.append(c)
                print(f"  {paint(str(n).rjust(2), C.BRIGHT_CYAN)}  {c.icon}  {c.help}")
                n += 1
        print()
        print(f"  {paint(' 0', C.GREY)}  🚪  Salir")
        hr()

        try:
            choice = input(paint("  ➤ ", C.MAGENTA) + "Elige una opción (número o nombre) › ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            ok("¡Hasta luego! 👋")
            return
        if choice in ("0", "q", "salir", "exit"):
            print()
            ok("¡Hasta luego! 👋")
            return

        cmd: Cmd | None = None
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(numbered):
                cmd = numbered[idx]
        else:
            cmd = resolve(choice.lower())
        if not cmd or not cmd.group:  # rechaza también comandos ocultos (p.ej. hookcheck)
            warn("Opción no válida.")
            continue

        if cmd.needs_repo and not is_git_repo():
            warn("Este proyecto aún no es un repositorio Git. Usa 'setup' (Configuración).")
            input(dim("\n  Pulsa Enter para volver…"))
            continue

        print()
        ns = _menu_namespace()
        if cmd.msg_prompt:
            try:
                msg = prompt(cmd.msg_prompt)
            except (KeyboardInterrupt, EOFError):
                continue
            if cmd.msg_required and not msg:
                warn("Este comando necesita un mensaje.")
                input(dim("\n  Pulsa Enter para volver…"))
                continue
            if cmd.name == "tag":
                ns.name = msg
            else:
                ns.message = msg

        try:
            cmd.func(ns)
        except subprocess.CalledProcessError as exc:
            print()
            err(f"Git devolvió un error (código {exc.returncode}).")
            explain_git_error(getattr(exc, "stderr", "") or "")
        except (KeyboardInterrupt, EOFError):
            print()
            warn("Operación cancelada.")
        except Exception as exc:  # noqa: BLE001
            print()
            err(f"Error inesperado: {exc}")

        input(dim("\n  Pulsa Enter para volver al menú…"))


def _menu_namespace() -> argparse.Namespace:
    """Namespace con todos los defaults del registro (para el menú)."""
    defaults: dict = {"message": "", "name": "", "url": "", "dest": "", "term": "",
                      "path": "", "source": "", "output": "", "version": "",
                      "action": "", "mode": "", "count": 15, "interval": 0,
                      "full": False, "watch": False, "guided": False,
                      "fix": False, "force_protected": False,
                      "global_conf": False, "export_path": "", "import_path": ""}
    return argparse.Namespace(**defaults)


# =============================================================================
# 12 · CLI
# =============================================================================

def _add_global_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("-y", "--yes", action="store_true", help="Confirma todo automáticamente.")
    p.add_argument("-n", "--dry-run", action="store_true", help="Simula sin ejecutar cambios.")
    p.add_argument("--no-color", action="store_true", help="Desactiva los colores.")
    p.add_argument("-q", "--quiet", action="store_true", help="Menos mensajes.")
    p.add_argument("--allow-secrets", action="store_true", help="Permite commitear secretos detectados.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync.py",
        description=f"{APP_NAME} · Sincronizador Git profesional y genérico.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    _add_global_flags(parser)
    sub = parser.add_subparsers(dest="command", required=False)

    for c in REGISTRY:
        p = sub.add_parser(c.name, aliases=list(c.aliases), help=c.help or None)
        _add_global_flags(p)
        for a in c.args:
            p.add_argument(*a.flags, **a.kw)
        p.set_defaults(func=c.func, _cmd=c.name)
    return parser


def _apply_flags(args) -> None:
    argv = sys.argv[1:]
    if "--" in argv:  # no interpretar como flags lo que va tras el separador '--'
        argv = argv[:argv.index("--")]
    RT.assume_yes = getattr(args, "yes", False) or "-y" in argv or "--yes" in argv
    RT.dry_run = getattr(args, "dry_run", False) or "-n" in argv or "--dry-run" in argv
    RT.quiet = getattr(args, "quiet", False) or "-q" in argv or "--quiet" in argv
    RT.allow_secrets = getattr(args, "allow_secrets", False) or "--allow-secrets" in argv
    if getattr(args, "no_color", False) or "--no-color" in argv:
        RT.color = False


def _maybe_suggest(argv: list[str]) -> None:
    """Si el primer argumento parece un comando mal escrito, sugiere el correcto."""
    if not argv or argv[0].startswith("-"):
        return
    cand = argv[0]
    known = list(BY_NAME) + list(BY_ALIAS) + ["-h", "--help", "--version"]
    if cand in known:
        return
    matches = difflib.get_close_matches(cand, list(BY_NAME), n=1, cutoff=0.6)
    if matches:
        RT.color = supports_color()
        err(f"Comando desconocido: '{cand}'.")
        info(f"¿Quisiste decir '{bold(matches[0])}'?")
        raise SystemExit(2)


def main() -> int:
    RT.color = supports_color()
    RT.width = ui_width()

    if not git_available():
        err("Git no está instalado o no está en el PATH.")
        print("\n  Instala Git desde https://git-scm.com y vuelve a intentarlo.")
        return 1

    _maybe_suggest(sys.argv[1:])
    parser = build_parser()
    args = parser.parse_args()
    _apply_flags(args)

    if RT.dry_run:
        warn("Modo simulación: no se realizará ningún cambio real.")

    if not getattr(args, "command", None):
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print()
            info("Operación cancelada.")
        return 0

    cmd = resolve(getattr(args, "_cmd", args.command))
    if cmd and cmd.needs_repo and not is_git_repo():
        err("Este directorio no es un repositorio Git.")
        print("\n  Ejecuta primero:  " + bold("python sync.py setup"))
        return 1

    try:
        result = args.func(args)
        return 0 if result is not False else 1
    except subprocess.CalledProcessError as exc:
        err(f"Git devolvió un error (código {exc.returncode}).")
        explain_git_error(getattr(exc, "stderr", "") or "")
        return exc.returncode or 1
    except KeyboardInterrupt:
        print()
        warn("Operación cancelada por el usuario.")
        return 130
    except Exception as exc:  # noqa: BLE001
        err(f"Error inesperado: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
