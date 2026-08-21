"""
G-SYNC · Sincronizador Git profesional y genérico para cualquier proyecto.
================================================================================

Una única herramienta, autocontenida y portable: copia este archivo a la raíz
de CUALQUIER proyecto y estará listo para sincronizar con GitHub (o cualquier
remoto Git) sin recordar comandos.

USO INTERACTIVO (menú bonito):
    python sync.py

USO DIRECTO (CLI):
    python sync.py setup                 # asistente: crea repo, remoto, rama, .gitignore
    python sync.py status                # estado detallado del repositorio
    python sync.py pull                  # traer cambios (rebase, con auto-stash)
    python sync.py push  -m "mensaje"    # add + commit + push
    python sync.py commit -m "mensaje"   # solo commit
    python sync.py save                  # guardado rápido (commit automático + push)
    python sync.py sync  -m "mensaje"    # commit + fetch + rebase + push (todo en uno)
    python sync.py log                   # historial bonito
    python sync.py diff                  # ver cambios pendientes
    python sync.py branch                # gestionar ramas (listar/crear/cambiar/borrar)
    python sync.py stash                 # guardar/recuperar cambios temporales
    python sync.py undo                  # deshacer el último commit (conservando cambios)
    python sync.py discard               # descartar cambios locales (¡peligroso!)
    python sync.py clone <url>           # clonar un repositorio
    python sync.py remote                # gestionar remotos (origin, etc.)
    python sync.py ignore                # crear/ampliar .gitignore
    python sync.py tag  -m "v1.0.0"      # crear una etiqueta/versión
    python sync.py watch                 # MODO AUTOMÁTICO: sincroniza cada N minutos
    python sync.py config                # editar la configuración del proyecto
    python sync.py doctor                # diagnóstico completo

OPCIONES GLOBALES:
    -y, --yes        No preguntar: confirma todo automáticamente.
    -n, --dry-run    Simulación: muestra qué haría sin ejecutar cambios.
        --no-color   Desactiva los colores.
    -q, --quiet      Menos mensajes.

CONFIGURACIÓN (se guarda en '.sync.json' dentro del proyecto):
    {
        "remote": "https://github.com/usuario/proyecto.git",
        "branch": "main",
        "pull_strategy": "rebase",       # rebase | merge
        "auto_stash": true,               # guarda cambios antes de pull y los restaura
        "commit_template": "Actualización {date}",
        "confirm": true,                  # pedir confirmación en operaciones sensibles
        "watch_interval": 300,            # segundos entre sincronizaciones en modo watch
        "protected_branches": ["main", "master", "production"]
    }

También puedes usar variables de entorno: SYNC_REPO_URL y SYNC_BRANCH.

Requisitos: Git instalado y acceso al repositorio (HTTPS con token o SSH).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import unicodedata
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Callable

# La consola de Windows suele usar cp1252 y no admite los caracteres de caja
# ni los emojis: forzamos UTF-8 en la salida (con reemplazo por si acaso).
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    except (AttributeError, ValueError):
        pass

APP_NAME = "G-SYNC"
APP_VERSION = "2.0"
SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_FILE = SCRIPT_DIR / ".sync.json"

ENV_REPO_URL = os.environ.get("SYNC_REPO_URL", "").strip()
ENV_BRANCH = os.environ.get("SYNC_BRANCH", "").strip()


# =============================================================================
# ESTADO GLOBAL DE EJECUCIÓN (flags)
# =============================================================================

class Runtime:
    assume_yes: bool = False
    dry_run: bool = False
    quiet: bool = False
    color: bool = True


RT = Runtime()


# =============================================================================
# COLORES / UI
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
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_BLUE = "\033[94m"


def _enable_windows_ansi() -> bool:
    """Activa el procesamiento de secuencias ANSI en la consola de Windows."""
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        # Habilita ENABLE_VIRTUAL_TERMINAL_PROCESSING en stdout (-11).
        handle = kernel32.GetStdHandle(-11)
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


def hr(width: int = 64) -> None:
    print(paint("─" * width, C.GREY))


def section(title: str, icon: str = "") -> None:
    print()
    head = f"{icon}  {title}".strip()
    line = paint("┄┄ ", C.CYAN) + bold(head) + " "
    pad = max(0, 60 - len(head) - 4)
    print(line + paint("┄" * pad, C.GREY))


def box(title: str, lines: list[str], width: int = 62, color: str = C.BRIGHT_CYAN) -> None:
    """Dibuja una caja bonita con título."""
    print()
    print(paint("╭" + "─" * width + "╮", color))
    tw = _visible_len(title)
    left = max(0, (width - tw - 2) // 2)
    right = max(0, width - tw - 2 - left)
    print(paint("│", color) + " " * (left + 1) + bold(title) +
          " " * (right + 1) + paint("│", color))
    print(paint("├" + "─" * width + "┤", color))
    for ln in lines:
        pad = max(0, width - _visible_len(ln) - 1)
        print(paint("│", color) + " " + ln + " " * pad + paint("│", color))
    print(paint("╰" + "─" * width + "╯", color))


def _char_width(ch: str) -> int:
    """Ancho en columnas de un carácter (emojis y CJK cuentan como 2)."""
    if unicodedata.combining(ch):
        return 0
    if unicodedata.east_asian_width(ch) in ("W", "F"):
        return 2
    # Rango de emojis y símbolos anchos habituales.
    if ord(ch) >= 0x1F000 or 0x2190 <= ord(ch) <= 0x2B55:
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


def prompt(question: str, default: str = "") -> str:
    hint = f" {dim('[' + default + ']')}" if default else ""
    try:
        answer = input(paint("  ? ", C.MAGENTA) + question + hint + " › ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        raise
    return answer or default


def confirm(question: str, *, default: bool = False) -> bool:
    """Pide confirmación. Respeta --yes."""
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


# =============================================================================
# CONFIGURACIÓN
# =============================================================================

@dataclass
class SyncConfig:
    remote: str = ""
    branch: str = ""
    pull_strategy: str = "rebase"          # rebase | merge
    auto_stash: bool = True
    commit_template: str = "Actualización {date}"
    confirm: bool = True
    watch_interval: int = 300
    protected_branches: list[str] = field(
        default_factory=lambda: ["main", "master", "production"]
    )


def load_config() -> SyncConfig:
    cfg = SyncConfig(remote=ENV_REPO_URL, branch=ENV_BRANCH)
    if not CONFIG_FILE.exists():
        return cfg
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        warn(f"No se pudo leer {CONFIG_FILE.name}: {exc}")
        return cfg

    cfg.remote = str(data.get("remote", "")).strip() or ENV_REPO_URL
    cfg.branch = str(data.get("branch", "")).strip() or ENV_BRANCH
    cfg.pull_strategy = str(data.get("pull_strategy", cfg.pull_strategy)).strip() or "rebase"
    cfg.auto_stash = bool(data.get("auto_stash", cfg.auto_stash))
    cfg.commit_template = str(data.get("commit_template", cfg.commit_template))
    cfg.confirm = bool(data.get("confirm", cfg.confirm))
    cfg.watch_interval = int(data.get("watch_interval", cfg.watch_interval) or 300)
    pb = data.get("protected_branches")
    if isinstance(pb, list) and pb:
        cfg.protected_branches = [str(x) for x in pb]
    return cfg


def save_config(cfg: SyncConfig) -> None:
    if RT.dry_run:
        info(f"[simulación] Guardaría configuración en {CONFIG_FILE.name}")
        return
    CONFIG_FILE.write_text(
        json.dumps(asdict(cfg), indent=4, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


CONFIG = load_config()


def ask_confirm(question: str, *, default: bool = False) -> bool:
    """Confirmación que respeta la preferencia 'confirm' del proyecto."""
    if not CONFIG.confirm:
        return True
    return confirm(question, default=default)


# =============================================================================
# GIT — utilidades
# =============================================================================

# Comandos que MODIFICAN el repositorio (se saltan en --dry-run).
_MUTATING = {
    "init", "add", "commit", "push", "pull", "fetch", "merge", "rebase",
    "reset", "checkout", "switch", "branch", "stash", "clone", "tag",
    "remote", "clean", "restore", "revert",
}


def git_available() -> bool:
    return shutil.which("git") is not None


def run_git(*args: str, check: bool = True, capture: bool = False,
            cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = ["git", *args]
    subcmd = args[0] if args else ""

    if RT.dry_run and subcmd in _MUTATING and not capture:
        # No mutamos nada en modo simulación (los read-only sí se ejecutan).
        print(paint("  ~ ", C.YELLOW) + dim(f"[simulación] {' '.join(cmd)}"))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    if not capture and not RT.quiet:
        print(paint("  $ ", C.GREY) + dim(" ".join(cmd)))

    return subprocess.run(
        cmd, cwd=str(cwd or SCRIPT_DIR), text=True,
        capture_output=capture, check=check,
        encoding="utf-8", errors="replace",
    )


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run_git(*args, check=check)


def git_out(*args: str) -> str:
    res = run_git(*args, check=False, capture=True)
    return (res.stdout or "").strip()


def is_git_repo() -> bool:
    res = run_git("rev-parse", "--is-inside-work-tree", check=False, capture=True)
    return res.returncode == 0 and res.stdout.strip() == "true"


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
    out = git_out("stash", "list")
    return len([x for x in out.splitlines() if x.strip()])


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
    return branch in CONFIG.protected_branches


# =============================================================================
# REMOTO / SETUP
# =============================================================================

def ensure_remote(interactive: bool = True) -> bool:
    if remote_url():
        return True
    url = CONFIG.remote or ENV_REPO_URL
    if not url and interactive and sys.stdin and sys.stdin.isatty():
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


# =============================================================================
# ACCIONES
# =============================================================================

def cmd_setup(args) -> bool:
    box(f"{APP_NAME} · Asistente de configuración", [
        dim("  Vamos a preparar este proyecto para sincronizar con Git."),
        f"  {dim('Directorio:')} {SCRIPT_DIR}",
    ])

    # 1. Repositorio -----------------------------------------------------------
    section("Repositorio Git", "📁")
    if not is_git_repo():
        info("Este directorio todavía no es un repositorio Git.")
        if not ask_confirm("¿Inicializar un repositorio Git aquí?", default=True):
            warn("Configuración cancelada.")
            return False
        git("init")
        branch = args.branch or CONFIG.branch or "main"
        git("branch", "-M", branch)
        ok("Repositorio Git inicializado.")
    else:
        ok("Ya es un repositorio Git.")

    # 2. Remoto ----------------------------------------------------------------
    section("Repositorio remoto", "🔗")
    existing = remote_url()
    if existing:
        print(f"  Remoto actual: {bold(existing)}")
        new_url = args.url or ""
        if not new_url and not RT.assume_yes:
            new_url = prompt("Nueva URL (Enter para conservar la actual)")
        if new_url and new_url != existing:
            if ask_confirm(f"¿Cambiar origin a '{new_url}'?", default=True):
                git("remote", "set-url", "origin", new_url)
                CONFIG.remote = new_url
                ok("Remoto actualizado.")
        else:
            CONFIG.remote = existing
    else:
        url = args.url or CONFIG.remote or ENV_REPO_URL
        if not url and not RT.assume_yes:
            print(dim("    Ejemplo: https://github.com/usuario/proyecto.git"))
            url = prompt("URL del repositorio remoto (Enter para omitir)")
        if url:
            git("remote", "add", "origin", url)
            CONFIG.remote = url
            ok(f"Remoto 'origin' añadido: {bold(url)}")
        else:
            warn("No se ha configurado ningún remoto (podrás hacerlo después).")

    # 3. Rama ------------------------------------------------------------------
    section("Rama principal", "🌿")
    branch = args.branch or CONFIG.branch or current_branch() or "main"
    if not args.branch and not RT.assume_yes:
        branch = prompt("Rama principal", default=branch)
    if is_git_repo() and current_branch() != branch:
        if ask_confirm(f"¿Usar '{branch}' como rama principal?", default=True):
            git("branch", "-M", branch)
    CONFIG.branch = branch

    # 4. .gitignore ------------------------------------------------------------
    section("Archivo .gitignore", "📄")
    gitignore = SCRIPT_DIR / ".gitignore"
    if gitignore.exists():
        ok(".gitignore ya existe.")
    elif ask_confirm("¿Crear un .gitignore recomendado?", default=True):
        _write_gitignore()

    # 5. Guardar ---------------------------------------------------------------
    save_config(CONFIG)
    box("✔ Configuración guardada", [
        f"  {dim('Proyecto :')} {bold(SCRIPT_DIR.name)}",
        f"  {dim('Remoto   :')} {configured_remote() or paint('(sin configurar)', C.YELLOW)}",
        f"  {dim('Rama     :')} {current_branch()}",
        f"  {dim('Config   :')} {CONFIG_FILE.name}",
    ], color=C.BRIGHT_GREEN)

    print()
    info("La primera vez que subas, Git te pedirá autenticación.")
    print(dim("     En GitHub usa un Personal Access Token como contraseña,"))
    print(dim("     o configura una clave SSH."))
    print()
    ok("¡El proyecto está listo! Prueba: " + bold("python sync.py status"))
    return True


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

    # Cambios locales ----------------------------------------------------------
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
        for line in res.stdout.rstrip().splitlines():
            print("    " + _colorize_status_line(line))
    if stashes:
        print()
        info(f"Tienes {bold(str(stashes))} guardado(s) en stash.")

    # Sincronización con remoto ------------------------------------------------
    if remote_url():
        section("Sincronización con el remoto", "🔄")
        ahead, behind = ahead_behind()
        if ahead:
            warn(f"{bold(str(ahead))} commit(s) local(es) pendiente(s) de subir (push).")
        if behind:
            warn(f"{bold(str(behind))} commit(s) remoto(s) pendiente(s) de traer (pull).")
        if not ahead and not behind:
            ok("Local y remoto están sincronizados.")

    # Últimos commits ----------------------------------------------------------
    if has_commits():
        section("Últimos commits", "🕑")
        log = git_out("log", "-5", "--color=always" if RT.color else "--no-color",
                      "--pretty=format:  %C(yellow)%h%Creset %s %C(dim)· %ar · %an%Creset")
        print(log)
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


def _auto_stash_wrap(action: Callable[[], bool], reason: str) -> bool:
    """Guarda cambios en stash antes de 'action' y los restaura al terminar."""
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
        if not ask_confirm("¿Continuar de todas formas?"):
            info("Pull cancelado.")
            return False
    elif not ask_confirm("¿Traer los cambios del remoto?", default=True):
        info("Pull cancelado.")
        return False

    def do_pull() -> bool:
        try:
            git("pull", strategy, "origin", branch)
        except subprocess.CalledProcessError:
            err("El pull no pudo completarse (posible conflicto).")
            _print_rebase_help()
            return False
        ok("Cambios descargados correctamente.")
        return True

    return _auto_stash_wrap(do_pull, "traer cambios")


def create_commit(message: str, *, silent: bool = False) -> bool:
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
    if not silent:
        print(f"  {dim('Mensaje:')} {bold(message)}")
    git("commit", "-m", message)
    if not silent:
        ok("Commit creado correctamente.")
    return True


def cmd_commit(args) -> bool:
    section("Commit (sin subir)", "📝")
    if not has_changes():
        info("No hay cambios locales que confirmar.")
        return True
    message = (args.message or "").strip()
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

    if is_protected(branch):
        warn(f"Vas a subir a la rama protegida '{bold(branch)}'.")

    if has_changes():
        message = (args.message or "").strip() or commit_message()
        print(f"  {dim('Se creará el commit:')} {bold(message)}")
        if not ask_confirm(f"¿Crear el commit y subirlo a '{branch}'?", default=True):
            info("Push cancelado.")
            return False
        create_commit(message, silent=True)
        ok(f"Commit creado: {message}")
    elif not has_commits():
        warn("Todavía no existe ningún commit en este repositorio.")
        if not ask_confirm("¿Continuar?"):
            return False
    else:
        ahead, _ = ahead_behind()
        detail = f" ({ahead} pendiente(s))" if ahead else ""
        if not ask_confirm(f"¿Subir los commits locales a '{branch}'{detail}?", default=True):
            info("Push cancelado.")
            return False

    try:
        git("push", "-u", "origin", branch)
    except subprocess.CalledProcessError:
        err("No se pudieron subir los cambios.")
        info("El remoto puede tener commits que aún no tienes. Prueba con 'sync'.")
        return False
    ok("Cambios enviados correctamente al remoto. 🚀")
    return True


def cmd_save(args) -> bool:
    args.message = (args.message or "").strip() or commit_message()
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
    print(f"  {dim('Proyecto:')} {bold(SCRIPT_DIR.name)}   "
          f"{dim('Rama:')} {bold(branch)}")
    print(f"  {dim('Remoto  :')} {configured_remote()}")

    # 1. Commit ----------------------------------------------------------------
    if has_changes():
        message = (args.message or "").strip() or commit_message()
        section("Paso 1 · Confirmar cambios", "📝")
        print(f"  {dim('Commit:')} {bold(message)}")
        if not ask_confirm("¿Guardar estos cambios en un commit?", default=True):
            info("Sincronización cancelada.")
            return False
        if not create_commit(message, silent=True):
            return False
        ok("Cambios confirmados.")
    else:
        info("No hay cambios locales nuevos que confirmar.")

    if not ask_confirm("¿Iniciar la sincronización con el remoto?", default=True):
        info("Sincronización cancelada.")
        return False

    # 2. Fetch -----------------------------------------------------------------
    section("Paso 2 · Consultar el remoto", "📡")
    try:
        git("fetch", "origin")
    except subprocess.CalledProcessError:
        err("No se pudo contactar con el remoto. Revisa tu conexión o credenciales.")
        return False

    # 3. Rebase/merge ----------------------------------------------------------
    _, behind = ahead_behind()
    if behind:
        section("Paso 3 · Integrar cambios remotos", "🔀")
        info(f"El remoto tiene {bold(str(behind))} commit(s) nuevo(s).")
        strategy = "--rebase" if CONFIG.pull_strategy == "rebase" else "--no-rebase"
        try:
            git("pull", strategy, "origin", branch)
        except subprocess.CalledProcessError:
            err("Conflicto al integrar los cambios remotos.")
            _print_rebase_help()
            return False
    else:
        ok("No hay cambios nuevos en el remoto.")

    # 4. Push ------------------------------------------------------------------
    section("Paso 4 · Subir cambios", "⬆")
    try:
        git("push", "-u", "origin", branch)
    except subprocess.CalledProcessError:
        err("El push falló. El remoto pudo cambiar durante la sincronización.")
        return False

    print()
    box("✔ Sincronización completada", [
        paint("  Todo tu trabajo está guardado y sincronizado. 🎉", C.BRIGHT_GREEN),
    ], color=C.BRIGHT_GREEN)
    return True


def cmd_log(args) -> bool:
    section("Historial de commits", "🕑")
    if not has_commits():
        info("Todavía no hay commits.")
        return True
    n = str(getattr(args, "count", 15) or 15)
    fmt = ("%C(yellow)%h%Creset %C(auto)%d%Creset %s "
           "%C(dim)· %an · %ar%Creset")
    color = "--color=always" if RT.color else "--no-color"
    out = git_out("log", f"-{n}", "--graph", color, f"--pretty=format:{fmt}")
    print(out)
    return True


def cmd_diff(args) -> bool:
    section("Cambios pendientes", "🔍")
    if not has_changes():
        ok("No hay cambios locales.")
        return True
    color = "--color=always" if RT.color else "--no-color"
    stat = git_out("diff", "--stat", color)
    staged_stat = git_out("diff", "--cached", "--stat", color)
    if staged_stat:
        print(bold("  Preparados (staged):"))
        print(staged_stat)
        print()
    if stat:
        print(bold("  Sin preparar:"))
        print(stat)
    if getattr(args, "full", False):
        section("Diferencias completas", "")
        run_git("--no-pager", "diff", color, check=False)
        run_git("--no-pager", "diff", "--cached", color, check=False)
    else:
        print()
        info("Usa 'python sync.py diff --full' para ver las diferencias línea a línea.")
    return True


def cmd_branch(args) -> bool:
    section("Ramas", "🌿")
    current = current_branch()
    branches = [b.strip().lstrip("* ").strip()
                for b in git_out("branch").splitlines() if b.strip()]
    for b in branches:
        mark = paint("→ ", C.GREEN) if b == current else "  "
        prot = paint(" 🔒", C.YELLOW) if is_protected(b) else ""
        print(f"  {mark}{bold(b) if b == current else b}{prot}")

    target = getattr(args, "name", "") or ""
    if not target and not RT.assume_yes:
        print()
        print(dim("  Acciones: escribe un nombre para crear/cambiar, Enter para salir."))
        target = prompt("Rama (nueva o existente)")
    if not target:
        return True

    if target in branches:
        if ask_confirm(f"¿Cambiar a la rama '{target}'?", default=True):
            git("switch", target)
            ok(f"Ahora estás en '{target}'.")
    else:
        if ask_confirm(f"La rama '{target}' no existe. ¿Crearla y cambiar a ella?", default=True):
            git("switch", "-c", target)
            ok(f"Rama '{target}' creada.")
    return True


def cmd_stash(args) -> bool:
    section("Guardado temporal (stash)", "📦")
    stashes = git_out("stash", "list")
    action = getattr(args, "action", "") or ""

    if stashes:
        print(bold("  Guardados actuales:"))
        for line in stashes.splitlines():
            print("    " + dim(line))
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
        if ask_confirm("¿Recuperar el último stash?", default=True):
            git("stash", "pop")
            ok("Cambios recuperados.")
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
    git("reset", "--soft", "HEAD~1")
    ok("Commit deshecho. Tus cambios siguen en el área de trabajo.")
    return True


def cmd_discard(args) -> bool:
    section("Descartar cambios locales", "🗑")
    if not has_changes():
        info("No hay cambios locales que descartar.")
        return True
    modified, untracked, staged = changed_summary()
    err("¡ATENCIÓN! Esta operación es DESTRUCTIVA e irreversible.")
    print(f"  Se perderán: {paint(str(modified + staged) + ' cambio(s)', C.YELLOW)}"
          f" y {paint(str(untracked) + ' archivo(s) nuevo(s)', C.CYAN)}.")
    if not confirm("¿Seguro que quieres DESCARTAR todos los cambios locales?"):
        info("Cancelado. No se ha tocado nada.")
        return False
    if not confirm(paint("Confírmalo de nuevo: esto NO se puede deshacer", C.RED)):
        info("Cancelado.")
        return False
    git("reset", "--hard", "HEAD")
    git("clean", "-fd")
    ok("Cambios locales descartados.")
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
    if not ask_confirm("¿Clonar ahora?", default=True):
        return False
    cmd = ["clone", url]
    if dest:
        cmd.append(dest)
    try:
        run_git(*cmd, cwd=SCRIPT_DIR)
    except subprocess.CalledProcessError:
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
        if ask_confirm(f"¿Cambiar 'origin' a '{new_url}'?", default=True):
            git("remote", "set-url", "origin", new_url)
    else:
        git("remote", "add", "origin", new_url)
    CONFIG.remote = new_url
    save_config(CONFIG)
    ok(f"Remoto 'origin' → {bold(new_url)}")
    return True


def cmd_tag(args) -> bool:
    section("Etiquetas / versiones", "🏷")
    tags = git_out("tag", "--sort=-creatordate")
    if tags:
        print(bold("  Etiquetas existentes:"))
        for t in tags.splitlines()[:10]:
            print("    " + t)
        print()

    name = (getattr(args, "name", "") or "").strip()
    if not name:
        name = (getattr(args, "message", "") or "").strip()
    if not name and not RT.assume_yes:
        name = prompt("Nombre de la etiqueta (ej. v1.0.0)")
    if not name:
        return True

    if not ask_confirm(f"¿Crear la etiqueta '{name}'?", default=True):
        return False
    git("tag", "-a", name, "-m", name)
    ok(f"Etiqueta '{name}' creada.")
    if remote_url() and ask_confirm("¿Subir la etiqueta al remoto?", default=True):
        git("push", "origin", name)
        ok("Etiqueta subida.")
    return True


def cmd_ignore(args) -> bool:
    section("Archivo .gitignore", "📄")
    gitignore = SCRIPT_DIR / ".gitignore"
    if gitignore.exists():
        info(f".gitignore ya existe ({len(gitignore.read_text(encoding='utf-8').splitlines())} líneas).")
        if not ask_confirm("¿Añadir las reglas recomendadas al final?", default=False):
            return True
        _write_gitignore(append=True)
    else:
        _write_gitignore()
    return True


def _write_gitignore(append: bool = False) -> None:
    content = """# --- G-Sync: .gitignore recomendado ---
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
env/
.pytest_cache/
.mypy_cache/

# Node
node_modules/
dist/
build/
.next/
*.log

# Entornos y secretos
.env
.env.*
*.local

# Sistema operativo
.DS_Store
Thumbs.db
desktop.ini

# Editores/IDE
.vscode/
.idea/
*.swp

# Bases de datos locales
*.sqlite
*.sqlite3
*.db
"""
    gitignore = SCRIPT_DIR / ".gitignore"
    if RT.dry_run:
        info("[simulación] Escribiría .gitignore")
        return
    if append and gitignore.exists():
        with gitignore.open("a", encoding="utf-8") as f:
            f.write("\n" + content)
        ok("Reglas añadidas a .gitignore.")
    else:
        gitignore.write_text(content, encoding="utf-8")
        ok(".gitignore creado.")


def cmd_watch(args) -> bool:
    interval = int(getattr(args, "interval", 0) or CONFIG.watch_interval or 300)
    box("👁  Modo automático (watch)", [
        dim(f"  Cada {interval}s se detectan cambios y se sincronizan solos."),
        dim("  Pulsa Ctrl+C para detener."),
    ], color=C.MAGENTA)
    if not ensure_remote():
        return False
    if not confirm(f"¿Iniciar sincronización automática cada {interval}s?", default=True):
        return False

    branch = current_branch()
    count = 0
    # En modo watch no queremos preguntas por cada ciclo.
    saved_confirm = CONFIG.confirm
    saved_yes = RT.assume_yes
    CONFIG.confirm = False
    RT.assume_yes = True
    RT.quiet = True
    try:
        while True:
            timestamp = datetime.now().strftime("%H:%M:%S")
            if has_changes():
                count += 1
                msg = commit_message()
                print(paint(f"\n[{timestamp}] ", C.GREY) +
                      paint("Cambios detectados → sincronizando…", C.CYAN))
                create_commit(msg, silent=True)
                run_git("pull", "--rebase", "origin", branch, check=False)
                res = run_git("push", "-u", "origin", branch, check=False)
                if res.returncode == 0:
                    ok(f"Sincronización #{count} completada ({msg}).")
                else:
                    warn("No se pudo subir en este ciclo; se reintentará.")
            else:
                print(paint(f"[{timestamp}] ", C.GREY) + dim("Sin cambios."))
            time.sleep(interval)
    except (KeyboardInterrupt, EOFError):
        print()
        info(f"Modo automático detenido. Sincronizaciones realizadas: {count}.")
    finally:
        CONFIG.confirm = saved_confirm
        RT.assume_yes = saved_yes
        RT.quiet = False
    return True


def cmd_config(args) -> bool:
    box("🔧 Configuración del proyecto", [
        f"  {dim('Archivo:')} {CONFIG_FILE}",
    ])
    print()
    print(bold("  Valores actuales:"))
    print(f"    Remoto           : {configured_remote() or dim('(ninguno)')}")
    print(f"    Rama             : {CONFIG.branch or current_branch()}")
    print(f"    Estrategia pull  : {CONFIG.pull_strategy}")
    print(f"    Auto-stash       : {'sí' if CONFIG.auto_stash else 'no'}")
    print(f"    Confirmaciones   : {'sí' if CONFIG.confirm else 'no'}")
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
        new_stash = prompt("Auto-stash (s/n)", default="s" if CONFIG.auto_stash else "n")
        new_confirm = prompt("Pedir confirmaciones (s/n)", default="s" if CONFIG.confirm else "n")
        new_template = prompt("Plantilla de commit", default=CONFIG.commit_template)
        new_interval = prompt("Intervalo watch (segundos)", default=str(CONFIG.watch_interval))
    except (KeyboardInterrupt, EOFError):
        print()
        info("Configuración cancelada.")
        return False

    if new_remote and new_remote != remote_url():
        if is_git_repo():
            if remote_url():
                if ask_confirm("¿Actualizar también el remoto 'origin' en Git?", default=True):
                    git("remote", "set-url", "origin", new_remote)
            else:
                git("remote", "add", "origin", new_remote)
        CONFIG.remote = new_remote

    CONFIG.branch = new_branch or CONFIG.branch
    CONFIG.pull_strategy = "merge" if new_strategy.lower().startswith("m") else "rebase"
    CONFIG.auto_stash = new_stash.lower().startswith("s")
    CONFIG.confirm = new_confirm.lower().startswith("s")
    CONFIG.commit_template = new_template or CONFIG.commit_template
    try:
        CONFIG.watch_interval = max(10, int(new_interval))
    except ValueError:
        pass

    save_config(CONFIG)
    ok("Configuración guardada.")
    return True


def cmd_doctor(_args) -> bool:
    box("🩺 Diagnóstico", [dim("  Comprobando el entorno de trabajo…")])
    problems = 0

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
    name = git_out("config", "user.name")
    email = git_out("config", "user.email")
    if name and email:
        ok(f"Configurado como: {name} <{email}>")
    else:
        warn("Falta configurar tu identidad de Git:")
        print(dim('     git config --global user.name "Tu Nombre"'))
        print(dim('     git config --global user.email "tu@email.com"'))
        problems += 1

    section("Remoto", "")
    remote = remote_url()
    if remote:
        ok(f"origin → {remote}")
        info("Comprobando acceso al remoto…")
        res = run_git("ls-remote", "--heads", "origin", check=False, capture=True)
        if res.returncode == 0:
            ok("El remoto responde correctamente.")
        else:
            warn("No se pudo acceder al remoto. Revisa credenciales (token/SSH).")
            problems += 1
    else:
        warn("No existe el remoto 'origin'.")
        problems += 1

    section("Rama", "")
    ok(f"Rama actual: {current_branch()}")

    section("Configuración", "")
    if CONFIG_FILE.exists():
        ok(f"Configuración en {CONFIG_FILE.name}.")
    else:
        info("Sin .sync.json (se usan valores por defecto y variables de entorno).")

    print()
    if problems:
        warn(f"Diagnóstico terminado con {problems} aviso(s).")
    else:
        box("✔ Todo correcto", [paint("  No se detectaron problemas.", C.BRIGHT_GREEN)],
            color=C.BRIGHT_GREEN)
    return problems == 0


def _print_rebase_help() -> None:
    print()
    print(bold("  ¿Conflicto de rebase? Sigue estos pasos:"))
    print(dim("    1. Edita los archivos en conflicto y guarda."))
    print(dim("    2. git add <archivos>"))
    print(dim("    3. git rebase --continue"))
    print(dim("  Para cancelar todo el proceso:  git rebase --abort"))


# =============================================================================
# MENÚ INTERACTIVO
# =============================================================================

MENU = [
    ("1", "📊  Estado del repositorio", "status"),
    ("2", "⬇   Traer cambios (pull)", "pull"),
    ("3", "⬆   Subir cambios (push)", "push"),
    ("4", "💾  Guardar rápido (commit auto + push)", "save"),
    ("5", "🔄  Sincronizar (commit + rebase + push)", "sync"),
    ("6", "📝  Crear commit (sin subir)", "commit"),
    ("sep", "", None),
    ("7", "🕑  Historial (log)", "log"),
    ("8", "🔍  Ver cambios (diff)", "diff"),
    ("9", "🌿  Ramas", "branch"),
    ("10", "📦  Guardado temporal (stash)", "stash"),
    ("sep", "", None),
    ("11", "↩   Deshacer último commit", "undo"),
    ("12", "🗑   Descartar cambios locales", "discard"),
    ("13", "🏷   Etiquetas / versiones", "tag"),
    ("14", "👁   Modo automático (watch)", "watch"),
    ("sep", "", None),
    ("15", "⚙   Configurar proyecto (setup)", "setup"),
    ("16", "🔧  Configuración avanzada", "config"),
    ("17", "🩺  Diagnóstico (doctor)", "doctor"),
    ("0", "🚪  Salir", None),
]

ACTIONS: dict[str, Callable] = {
    "status": cmd_status, "pull": cmd_pull, "push": cmd_push, "save": cmd_save,
    "sync": cmd_sync, "commit": cmd_commit, "log": cmd_log, "diff": cmd_diff,
    "branch": cmd_branch, "stash": cmd_stash, "undo": cmd_undo, "discard": cmd_discard,
    "tag": cmd_tag, "watch": cmd_watch, "setup": cmd_setup, "config": cmd_config,
    "doctor": cmd_doctor, "clone": cmd_clone, "remote": cmd_remote, "ignore": cmd_ignore,
}

# Comandos que no requieren un repositorio ya inicializado.
NO_REPO_OK = {"setup", "clone", "doctor", "config"}


def print_header() -> None:
    branch = current_branch() if is_git_repo() else (CONFIG.branch or "main")
    remote = configured_remote()
    title = f"{APP_NAME}  ·  Gestor de sincronización Git   v{APP_VERSION}"

    print()
    print(paint("╭" + "─" * 62 + "╮", C.BRIGHT_BLUE))
    print(paint("│", C.BRIGHT_BLUE) + bold(title.center(62)) + paint("│", C.BRIGHT_BLUE))
    print(paint("╰" + "─" * 62 + "╯", C.BRIGHT_BLUE))

    print(f"  {dim('Proyecto')}  {bold(SCRIPT_DIR.name)}")
    print(f"  {dim('Rama')}      {branch}" +
          (paint("  🔒", C.YELLOW) if is_protected(branch) else ""))
    print(f"  {dim('Remoto')}    {remote or paint('(sin configurar — usa la opción 15)', C.YELLOW)}")

    if is_git_repo():
        modified, untracked, staged = changed_summary()
        total = modified + untracked
        if total or staged:
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


def _menu_needs_message(command: str) -> str | None:
    """Pide mensaje de commit para los comandos que lo usan. Devuelve None si se cancela."""
    if command == "commit":
        msg = prompt("Mensaje del commit")
        if not msg:
            warn("El commit necesita un mensaje.")
            return None
        return msg
    if command in {"push", "sync", "save", "tag"}:
        label = "Nombre de la etiqueta" if command == "tag" else "Mensaje del commit (Enter = automático)"
        return prompt(label)
    return ""


def interactive_menu() -> None:
    while True:
        print_header()
        print()
        for key, label, command in MENU:
            if key == "sep":
                print(dim("  " + "·" * 30))
                continue
            print(f"  {paint(key.rjust(2), C.BRIGHT_CYAN)}  {label}")
        hr()

        try:
            choice = input(paint("  ➤ ", C.MAGENTA) + "Elige una opción › ").strip()
        except (KeyboardInterrupt, EOFError):
            print()
            info("¡Hasta luego! 👋")
            return

        entry = next((m for m in MENU if m[0] == choice and m[0] != "sep"), None)
        if not entry:
            warn("Opción no válida.")
            continue
        _key, _label, command = entry
        if command is None:
            print()
            ok("¡Hasta luego! 👋")
            return

        if command not in NO_REPO_OK and not is_git_repo():
            warn("Este proyecto aún no es un repositorio Git. Usa la opción 15 (Configurar).")
            input(dim("\n  Pulsa Enter para volver…"))
            continue

        print()
        args = argparse.Namespace(
            command=command, message="", url="", branch="", name="",
            action="", dest="", count=15, full=False, interval=0,
        )
        if command in {"commit", "push", "sync", "save", "tag"}:
            msg = _menu_needs_message(command)
            if msg is None:
                input(dim("\n  Pulsa Enter para volver…"))
                continue
            if command == "tag":
                args.name = msg
            else:
                args.message = msg

        try:
            ACTIONS[command](args)
        except subprocess.CalledProcessError as exc:
            print()
            err(f"Git devolvió un error (código {exc.returncode}).")
        except (KeyboardInterrupt, EOFError):
            print()
            warn("Operación cancelada.")
        except Exception as exc:  # noqa: BLE001
            print()
            err(f"Error inesperado: {exc}")

        input(dim("\n  Pulsa Enter para volver al menú…"))


# =============================================================================
# CLI
# =============================================================================

def _add_global_flags(p: argparse.ArgumentParser) -> None:
    p.add_argument("-y", "--yes", action="store_true", help="Confirma todo automáticamente.")
    p.add_argument("-n", "--dry-run", action="store_true", help="Simula sin ejecutar cambios.")
    p.add_argument("--no-color", action="store_true", help="Desactiva los colores.")
    p.add_argument("-q", "--quiet", action="store_true", help="Menos mensajes.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sync.py",
        description=f"{APP_NAME} · Sincronizador Git profesional y genérico.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {APP_VERSION}")
    _add_global_flags(parser)

    sub = parser.add_subparsers(dest="command", required=False)

    def add(name, func, help_text):
        p = sub.add_parser(name, help=help_text)
        _add_global_flags(p)
        p.set_defaults(func=func)
        return p

    setup = add("setup", cmd_setup, "Asistente: inicializa Git, remoto, rama y .gitignore.")
    setup.add_argument("--url", default="", help="URL del repositorio remoto.")
    setup.add_argument("--branch", default="", help="Rama principal.")

    add("status", cmd_status, "Muestra el estado detallado del repositorio.")
    add("pull", cmd_pull, "Trae cambios del remoto (rebase, con auto-stash).")

    commit = add("commit", cmd_commit, "Crea un commit sin subirlo.")
    commit.add_argument("-m", "--message", default="", help="Mensaje del commit.")

    push = add("push", cmd_push, "add + commit + push.")
    push.add_argument("-m", "--message", default="", help="Mensaje del commit.")

    save = add("save", cmd_save, "Guardado rápido: commit automático + push.")
    save.add_argument("-m", "--message", default="", help="Mensaje opcional.")

    sync = add("sync", cmd_sync, "Todo en uno: commit + fetch + rebase + push.")
    sync.add_argument("-m", "--message", default="", help="Mensaje del commit.")

    log = add("log", cmd_log, "Muestra el historial de commits.")
    log.add_argument("-c", "--count", type=int, default=15, help="Nº de commits.")

    diff = add("diff", cmd_diff, "Muestra los cambios pendientes.")
    diff.add_argument("--full", action="store_true", help="Diferencias línea a línea.")

    branch = add("branch", cmd_branch, "Lista, crea o cambia de rama.")
    branch.add_argument("name", nargs="?", default="", help="Rama a crear/cambiar.")

    stash = add("stash", cmd_stash, "Guarda o recupera cambios temporales.")
    stash.add_argument("action", nargs="?", default="", choices=["", "push", "pop"],
                       help="push (guardar) o pop (recuperar).")

    add("undo", cmd_undo, "Deshace el último commit (conserva los cambios).")
    add("discard", cmd_discard, "Descarta TODOS los cambios locales (destructivo).")

    clone = add("clone", cmd_clone, "Clona un repositorio.")
    clone.add_argument("url", nargs="?", default="", help="URL del repositorio.")
    clone.add_argument("dest", nargs="?", default="", help="Carpeta destino.")

    remote = add("remote", cmd_remote, "Gestiona los remotos (origin, etc.).")
    remote.add_argument("--url", default="", help="Nueva URL para origin.")

    ignore = add("ignore", cmd_ignore, "Crea o amplía el .gitignore.")

    tag = add("tag", cmd_tag, "Crea una etiqueta/versión.")
    tag.add_argument("-m", "--message", default="", help="Nombre de la etiqueta.")
    tag.add_argument("name", nargs="?", default="", help="Nombre de la etiqueta.")

    watch = add("watch", cmd_watch, "Modo automático: sincroniza cada N segundos.")
    watch.add_argument("-i", "--interval", type=int, default=0, help="Segundos entre ciclos.")

    add("config", cmd_config, "Edita la configuración del proyecto (.sync.json).")
    add("doctor", cmd_doctor, "Diagnóstico completo del entorno.")

    return parser


def _apply_flags(args) -> None:
    RT.assume_yes = getattr(args, "yes", False)
    RT.dry_run = getattr(args, "dry_run", False)
    RT.quiet = getattr(args, "quiet", False)
    if getattr(args, "no_color", False):
        RT.color = False


def main() -> int:
    RT.color = supports_color()

    if not git_available():
        RT.color = supports_color()
        err("Git no está instalado o no está en el PATH.")
        print("\n  Instala Git desde https://git-scm.com y vuelve a intentarlo.")
        return 1

    parser = build_parser()
    args = parser.parse_args()
    _apply_flags(args)

    if RT.dry_run:
        warn("Modo simulación: no se realizará ningún cambio real.")

    # Sin subcomando → menú interactivo.
    if not getattr(args, "command", None):
        try:
            interactive_menu()
        except KeyboardInterrupt:
            print()
            info("Operación cancelada.")
        return 0

    command = args.command
    if command not in NO_REPO_OK and not is_git_repo():
        err("Este directorio no es un repositorio Git.")
        print("\n  Ejecuta primero:  " + bold("python sync.py setup"))
        return 1

    try:
        result = args.func(args)
        return 0 if result is not False else 1
    except subprocess.CalledProcessError as exc:
        err(f"Git devolvió un error (código {exc.returncode}).")
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
