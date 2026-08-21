# G-SYNC · Sincronizador Git profesional y genérico

Una **única herramienta** (`sync.py`), autocontenida y portable, para sincronizar
cualquier proyecto con GitHub (o cualquier remoto Git) sin tener que recordar
comandos. Cópiala a la raíz de cualquier proyecto y lista.

- ✅ **Genérica**: la URL del repo y la rama se guardan por proyecto en `.sync.json`.
- 🎨 **Bonita**: menú interactivo con colores, cajas e iconos.
- 🛡️ **Segura**: avisos y confirmaciones antes de operaciones sensibles.
- 🤖 **Automática**: modo `watch` que sincroniza sola cada N segundos.
- 🧰 **Completa**: 20 comandos (status, sync, log, diff, stash, ramas, tags…).
- 🧪 **Simulación**: `--dry-run` muestra qué haría sin tocar nada.
- 🖥️ **Windows-ready**: colores ANSI y UTF-8 forzados en la consola de Windows.

---

## 📦 Requisitos

- **Python 3.9+**
- **Git** instalado y en el `PATH` ([git-scm.com](https://git-scm.com))
- Acceso al repositorio remoto (HTTPS con *token* o clave SSH)

No necesita instalar dependencias: usa solo la librería estándar de Python.

---

## 🚀 Inicio rápido

1. Copia `sync.py` a la raíz de tu proyecto.
2. Ejecuta el asistente de configuración:

   ```bash
   python sync.py setup
   ```

   Te preguntará la **URL del repositorio**, la **rama principal** y creará un
   `.gitignore` recomendado. Todo se guarda en `.sync.json`.

3. A partir de ahí, sincroniza cuando quieras:

   ```bash
   python sync.py sync -m "Mi primer cambio"
   ```

O simplemente abre el **menú interactivo** ejecutándolo sin argumentos:

```bash
python sync.py
```

---

## 🧭 Uso

### Menú interactivo

```bash
python sync.py
```

```
╭──────────────────────────────────────────────────────────────╮
│         G-SYNC  ·  Gestor de sincronización Git   v2.0         │
╰──────────────────────────────────────────────────────────────╯
  Proyecto  mi-proyecto
  Rama      main 🔒
  Remoto    https://github.com/usuario/mi-proyecto.git
  Cambios   2 modificado(s) · 1 nuevo(s)
  Remoto ⇅  ↑1

   1  📊  Estado del repositorio
   2  ⬇   Traer cambios (pull)
   3  ⬆   Subir cambios (push)
   4  💾  Guardar rápido (commit auto + push)
   5  🔄  Sincronizar (commit + rebase + push)
   ...
```

### Línea de comandos (CLI)

| Comando | Descripción |
|---|---|
| `setup` | Asistente: inicializa Git, remoto, rama y `.gitignore`. |
| `status` | Estado detallado (cambios, ahead/behind, últimos commits). |
| `pull` | Trae cambios del remoto (rebase, con auto-stash). |
| `push -m "msg"` | `add` + `commit` + `push` en un paso. |
| `commit -m "msg"` | Crea un commit sin subirlo. |
| `save` | Guardado rápido: commit automático + push. |
| `sync -m "msg"` | Todo en uno: commit + fetch + rebase + push. |
| `log` | Historial de commits (bonito, con grafo). |
| `diff` | Muestra los cambios pendientes (`--full` para ver el detalle). |
| `branch [nombre]` | Lista, crea o cambia de rama. |
| `stash [push\|pop]` | Guarda o recupera cambios temporales. |
| `undo` | Deshace el último commit conservando los cambios. |
| `discard` | Descarta **todos** los cambios locales (destructivo). |
| `clone <url>` | Clona un repositorio. |
| `remote` | Gestiona los remotos (origin, etc.). |
| `ignore` | Crea o amplía el `.gitignore`. |
| `tag -m "v1.0.0"` | Crea una etiqueta/versión (y la sube). |
| `watch` | **Modo automático**: sincroniza cada N segundos. |
| `config` | Edita la configuración del proyecto. |
| `doctor` | Diagnóstico completo del entorno. |

### Opciones globales

| Opción | Descripción |
|---|---|
| `-y`, `--yes` | No preguntar: confirma todo automáticamente. |
| `-n`, `--dry-run` | Simulación: muestra qué haría sin ejecutar cambios. |
| `--no-color` | Desactiva los colores. |
| `-q`, `--quiet` | Menos mensajes. |

---

## 🤖 Modo automático (`watch`)

Ideal para no pensar en Git: detecta cambios y los sube solo.

```bash
python sync.py watch                 # usa el intervalo de la config (300s por defecto)
python sync.py watch -i 60           # cada 60 segundos
```

Detén el modo automático con `Ctrl+C`.

---

## ⚙️ Configuración (`.sync.json`)

Se crea automáticamente en la raíz del proyecto. Ejemplo completo:

```json
{
    "remote": "https://github.com/usuario/proyecto.git",
    "branch": "main",
    "pull_strategy": "rebase",
    "auto_stash": true,
    "commit_template": "Actualización {date}",
    "confirm": true,
    "watch_interval": 300,
    "protected_branches": ["main", "master", "production"]
}
```

| Clave | Significado |
|---|---|
| `remote` | URL del repositorio remoto (origin). |
| `branch` | Rama principal del proyecto. |
| `pull_strategy` | `rebase` (recomendado) o `merge`. |
| `auto_stash` | Guarda tus cambios antes de un `pull` y los restaura después. |
| `commit_template` | Plantilla del mensaje automático (`{date}` se sustituye). |
| `confirm` | Si `false`, no pide confirmación en operaciones normales. |
| `watch_interval` | Segundos entre ciclos del modo `watch`. |
| `protected_branches` | Ramas que muestran un aviso extra al hacer push. |

Puedes editar todo esto cómodamente con:

```bash
python sync.py config
```

### Variables de entorno

Si no hay `.sync.json`, se usan (si existen):

- `SYNC_REPO_URL` — URL del repositorio.
- `SYNC_BRANCH` — rama principal.

---

## 🔐 Autenticación con GitHub

La primera vez que subas, Git te pedirá credenciales:

- **HTTPS**: usa un [Personal Access Token](https://github.com/settings/tokens)
  como contraseña (no tu contraseña de GitHub).
- **SSH**: configura una clave SSH y usa la URL `git@github.com:usuario/repo.git`.

Comprueba que todo está bien con:

```bash
python sync.py doctor
```

---

## 🩹 Solución de problemas

| Problema | Solución |
|---|---|
| `Git no está instalado` | Instálalo desde [git-scm.com](https://git-scm.com) y reinicia la terminal. |
| `Este directorio no es un repositorio Git` | Ejecuta `python sync.py setup`. |
| No se ven colores/emojis en Windows | Usa **Windows Terminal** o PowerShell reciente (el script fuerza UTF-8). |
| Conflicto durante `sync`/`pull` | Edita los archivos, `git add`, luego `git rebase --continue` (o `--abort`). |
| El push falla porque el remoto cambió | Ejecuta `python sync.py sync`. |

---

## 💡 Ejemplos

```bash
# Configurar un proyecto nuevo indicando la URL directamente
python sync.py setup --url https://github.com/usuario/proyecto.git --branch main

# Guardar y subir todo con un mensaje
python sync.py push -m "Añadido módulo de facturación"

# Guardado rápido sin pensar en el mensaje
python sync.py save

# Ver qué haría un sync, sin ejecutar nada
python sync.py sync --dry-run

# Sincronizar sin que pregunte nada (para scripts/automatizaciones)
python sync.py sync -y -m "Actualización automática"

# Crear una versión
python sync.py tag -m "v1.2.0"
```

---

## 📄 Licencia

Uso libre. Adáptalo a tus proyectos.
