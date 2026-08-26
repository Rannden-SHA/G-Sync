<div align="center">

# 🔄 G-SYNC

### Sincronizador Git profesional, seguro y genérico — en un solo archivo

Una **única herramienta** (`sync.py`), autocontenida, portable y **sin dependencias**
(solo la librería estándar de Python). Cópiala a la raíz de cualquier proyecto y
sincroniza con GitHub sin recordar comandos — con red de seguridad ante errores caros.

`v3.0`  ·  Python 3.9+  ·  Windows / Linux / macOS  ·  Interfaz en español

</div>

---

## ✨ Por qué G-Sync

| | |
|---|---|
| 🎯 **Genérica** | La URL del repo y la rama se guardan por proyecto en `.sync.json`. Un mismo archivo para todos tus proyectos. |
| 🎨 **Bonita y dinámica** | Menú por categorías, colores, cajas, tablas, **spinner** en operaciones de red, **sparkline** de actividad y ancho adaptable al terminal. |
| 🛡️ **Segura** | **Escáner de secretos** y de archivos enormes antes de cada commit, protección real de ramas y **copias de seguridad** antes de operaciones destructivas. |
| 🧠 **Robusta** | Traduce los errores de git a consejos claros, **reintenta** ante fallos de red y avisa si no hay conexión. |
| 🤖 **Automática** | Modo `watch` inteligente (debounce + reintentos) y sincronización **programada** en el sistema (Windows/Linux/mac). |
| 🚀 **Completa** | 30+ comandos: release con CHANGELOG, Pull Requests, rescate de trabajo perdido, búsqueda en el historial, y mucho más. |

---

## 📦 Requisitos

- **Python 3.9+**
- **Git** en el `PATH` ([git-scm.com](https://git-scm.com))
- Acceso al repositorio (HTTPS con *token* o clave SSH)
- *(Opcional)* **`gh`** (GitHub CLI) para crear Pull Requests directamente

No requiere `pip install` de nada.

---

## 🚀 Inicio rápido

```bash
# 1. Copia sync.py a la raíz de tu proyecto y lanza el asistente:
python sync.py setup

# 2. Sincroniza cuando quieras:
python sync.py sync -m "Mi primer cambio"
```

O abre el **menú interactivo** ejecutándolo sin argumentos:

```bash
python sync.py
```

```
   ____   ____
  / ___| / ___| _   _ _ __   ___
 | |  _  \___ \| | | | '_ \ / __|
 | |_| |  ___) | |_| | | | | (__
  \____| |____/ \__, |_| |_|\___|
                |___/
  Gestor de sincronización Git · v3.0

  Proyecto  mi-proyecto
  Rama      main 🔒
  Remoto    https://github.com/usuario/mi-proyecto.git
  Cambios   2 modificado(s) · 1 nuevo(s)
  Remoto ⇅  ↑1

┄┄ Trabajo diario ┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄┄
   1  📊  Estado detallado del repositorio.
   2  🔄  Todo en uno: commit + rebase + push.
   ...
```

---

## 🧭 Comandos

### Trabajo diario
| Comando | Alias | Descripción |
|---|---|---|
| `status` | `st`, `s` | Estado detallado + sparkline de actividad. |
| `sync` | `sy` | Todo en uno: commit + fetch + rebase + push. |
| `save` | | Guardado rápido (commit automático + push). |
| `push` | `ps`, `up` | add + commit + push. |
| `pull` | `pl` | Trae cambios del remoto (rebase + auto-stash). |
| `commit` | `ci` | Crea un commit. Con `--guided`: Conventional Commits. |
| `amend` | | Corrige el último commit (mensaje o añadir archivos). |

### Inspeccionar
| Comando | Alias | Descripción |
|---|---|---|
| `dashboard` | `panel` | Panel de estado. `--watch` para vista en vivo. |
| `log` | `lg` | Historial con grafo. `-c N` para el número. |
| `diff` | `df` | Cambios pendientes con barras. `--full` para el detalle. |
| `find` | | Busca en el historial por mensaje o por código. |
| `who` | | Contribuidores y actividad del repositorio. |

### Ramas y publicación
| Comando | Alias | Descripción |
|---|---|---|
| `branch` | `br` | Lista, crea o cambia de rama (tabla). |
| `stash` | | Guarda o recupera cambios temporales. |
| `tag` | | Crea una etiqueta/versión. |
| `release` | | Sube versión semántica + genera **CHANGELOG.md**. |
| `pr` | | Crea un **Pull Request** (con `gh` o abriendo el navegador). |

### Recuperación (red de seguridad)
| Comando | Descripción |
|---|---|
| `undo` | Deshace el último commit (conserva los cambios + snapshot). |
| `discard` | Descarta cambios locales (con copia de seguridad previa). |
| `rescue` | Recupera trabajo perdido navegando el **reflog**. |
| `restore` | Restaura **un archivo** a una versión anterior. |

### Automatización
| Comando | Descripción |
|---|---|
| `watch` | Modo automático inteligente (debounce + reintentos). |
| `schedule` | Programa la sincronización en el sistema (Windows/Linux/mac). |
| `hooks` | Instala/quita git hooks (validación antes de commit). |
| `history` | Registro de auditoría de sincronizaciones automáticas. |

### Configuración
| Comando | Descripción |
|---|---|
| `setup` | Asistente completo de configuración. |
| `config` | Configuración del proyecto/usuario (`--global`, `--export`, `--import`). |
| `protect` | Gestiona reglas de protección de ramas. |
| `ignore` | Crea/actualiza el `.gitignore` según el tipo de proyecto. |
| `remote` | Gestiona los remotos. |
| `clone` | Clona un repositorio. |
| `archive` | Exporta un `.zip` del proyecto (sin `.git`). |
| `doctor` | Diagnóstico completo del entorno (`--fix`). |
| `selftest` | Auto-tests internos de la herramienta. |

### Opciones globales
| Opción | Descripción |
|---|---|
| `-y`, `--yes` | No preguntar: confirma todo automáticamente. |
| `-n`, `--dry-run` | **Simulación**: muestra qué haría sin ejecutar nada. |
| `--no-color` | Desactiva los colores. |
| `-q`, `--quiet` | Menos mensajes. |
| `--allow-secrets` | Permite commitear aunque se detecten secretos. |

---

## 🛡️ Seguridad integrada

Antes de **cada commit**, G-Sync analiza lo que vas a guardar:

- **Escáner de secretos** — detecta claves de AWS/Google, tokens de GitHub/Slack,
  claves privadas, JWT y credenciales en variables (`PASSWORD=`, `API_KEY=`…).
  Si encuentra algo, **bloquea el commit** — y ni siquiera `-y` puede saltarse esta
  barrera: hay que pasar explícitamente `--allow-secrets`.
- **Archivos enormes** — avisa a partir de 5 MB y bloquea a partir de 95 MB
  (GitHub los rechazaría de todos modos).
- **Protección de ramas** — avisa (o bloquea, si lo configuras) al hacer push a
  `main`/`master`/`production` u otras ramas protegidas.

Y antes de operaciones **destructivas** (`undo`, `discard`, `rescue`), crea una
**copia de seguridad** (un *bundle* de git + tus archivos sin seguimiento) que
puedes recuperar con `rescue`.

---

## 🤖 Automatización

```bash
# Vigila cambios y sincroniza solo, tras unos segundos de calma:
python sync.py watch
python sync.py watch -i 60        # ciclo máximo cada 60 s

# Instala una tarea programada en el sistema (cada 30 min):
python sync.py schedule install -i 30
python sync.py schedule status
python sync.py schedule remove

# Instala un git hook que valida secretos/archivos grandes antes de cada commit:
python sync.py hooks install
```

---

## ⚙️ Configuración (`.sync.json`)

Se crea en la raíz del proyecto. Hay además una **configuración global** en
`~/.g-sync/config.json` (la del proyecto tiene prioridad).

```json
{
    "remote": "https://github.com/usuario/proyecto.git",
    "branch": "main",
    "pull_strategy": "rebase",
    "auto_stash": true,
    "commit_template": "Actualización {date}",
    "commit_style": "libre",
    "confirm_level": "smart",
    "secret_scan": true,
    "large_file_warn_mb": 5,
    "large_file_block_mb": 95,
    "watch_interval": 300,
    "watch_debounce": 15,
    "protected_branches": ["main", "master", "production"],
    "block_direct_push": false,
    "backup_keep": 10
}
```

Edítala cómodamente con `python sync.py config` (o `config --global`).
También funcionan las variables de entorno `SYNC_REPO_URL` y `SYNC_BRANCH`.

---

## 🔐 Autenticación con GitHub

- **HTTPS**: usa un [Personal Access Token](https://github.com/settings/tokens)
  como contraseña (no tu contraseña de GitHub).
- **SSH**: configura una clave SSH y usa la URL `git@github.com:usuario/repo.git`.

Comprueba que todo está bien con `python sync.py doctor`.

---

## 🩹 Solución de problemas

G-Sync **traduce** los errores de git a consejos claros. Aun así:

| Problema | Solución |
|---|---|
| `Git no está instalado` | Instálalo desde [git-scm.com](https://git-scm.com). |
| `Este directorio no es un repositorio Git` | Ejecuta `python sync.py setup`. |
| No se ven colores/emojis en Windows | Usa **Windows Terminal** (el script fuerza UTF-8 y ANSI). |
| `detected dubious ownership` (Windows) | `git config --global --add safe.directory "<ruta>"` |
| Conflicto durante `sync`/`pull` | Edita, `git add`, luego `git rebase --continue`. |
| El push falla porque el remoto cambió | Ejecuta `python sync.py sync`. |

---

## 💡 Ejemplos

```bash
python sync.py setup --url https://github.com/usuario/proyecto.git --branch main
python sync.py push -m "Añadido módulo de facturación"
python sync.py save                       # guardado rápido, mensaje automático
python sync.py commit --guided            # asistente de Conventional Commits
python sync.py release                     # nueva versión + CHANGELOG
python sync.py sync --dry-run              # ver qué haría, sin tocar nada
python sync.py sync -y -m "Auto"          # sin preguntas (para scripts)
python sync.py rescue                      # recuperar trabajo perdido
```

---

<div align="center">
<sub>Uso libre · Adáptalo a tus proyectos · Hecho para no volver a pelearte con git</sub>
</div>
