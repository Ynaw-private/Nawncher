#!/usr/bin/env bash
# Instalador de Nawncher 2.0.0 para Debian, Fedora y Arch (y derivados).
set -euo pipefail

APP_ID="nawncher"
APP_NAME="Nawncher"
APP_VERSION="2.0.0"

if [ -z "${HOME:-}" ]; then
    HOME="$(getent passwd "$(id -un)" | cut -d: -f6)"
    export HOME
fi

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
SRC_FILE="$SELF_DIR/src/nawncher.py"
ICON_ROOT="$SELF_DIR/data/icons"
LEGACY_DIR="$SELF_DIR/legacy"
README_FILE="$SELF_DIR/README.md"

MODE="user"
PREFIX=""
PREFIX_SET=0
ACTION="install"
DEPENDENCIES="ask"
PURGE=0
MIGRATE=1
DISTRO="unknown"
DISTRO_NAME="Linux"

usage() {
    cat <<'EOF'
Nawncher 2.0.0 - instalador

Uso:
  ./install.sh [opciones]

Opciones:
  --user              Instala solo para el usuario actual en ~/.local (por defecto).
  --system            Instala para todo el sistema en /usr (requiere sudo/root).
  --prefix DIR        Usa otra prefija de instalación (avanzado).
  --deps              Instala las dependencias con el gestor de la distribución.
  --no-deps           No comprueba ni instala dependencias.
  --no-migrate        No importa los datos de la antigua versión portable.
  --uninstall         Desinstala Nawncher (conserva ~/.nawncher).
  --purge             Con --uninstall, borra también ~/.nawncher.
  -h, --help          Muestra esta ayuda.
  --version           Muestra la versión del instalador.

Ejemplos:
  ./install.sh --user
  ./install.sh --user --deps
  sudo ./install.sh --system --deps
  ./install.sh --user --uninstall
  ./install.sh --user --uninstall --purge

Los datos de usuario se guardan siempre en ~/.nawncher:
  config.json, stats.json, games/, covers/, cache/, logs/
EOF
}

log()  { printf '%s\n' "$*"; }
warn() { printf 'Aviso: %s\n' "$*" >&2; }
die()  { printf 'Error: %s\n' "$*" >&2; exit 1; }

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --user)        MODE="user"; shift ;;
            --system)      MODE="system"; shift ;;
            --prefix)
                [ "$#" -ge 2 ] || die "--prefix necesita un directorio"
                PREFIX="$2"; PREFIX_SET=1; shift 2 ;;
            --prefix=*)    PREFIX="${1#*=}"; PREFIX_SET=1; shift ;;
            --deps)        DEPENDENCIES="yes"; shift ;;
            --no-deps)     DEPENDENCIES="no"; shift ;;
            --no-migrate)  MIGRATE=0; shift ;;
            --migrate)     MIGRATE=1; shift ;;
            --uninstall)   ACTION="uninstall"; shift ;;
            --purge)       PURGE=1; shift ;;
            -h|--help)     usage; exit 0 ;;
            --version)     printf '%s %s\n' "$APP_NAME" "$APP_VERSION"; exit 0 ;;
            *)             die "Opción desconocida: $1 (usa --help)" ;;
        esac
    done
}

detect_distro() {
    if [ -r /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        DISTRO_NAME="${PRETTY_NAME:-${NAME:-Linux}}"
        local key="${ID:-} ${ID_LIKE:-}"
        case " $key " in
            *debian*|*ubuntu*|*linuxmint*|*pop*) DISTRO="debian" ;;
            *fedora*|*rhel*|*centos*|*rocky*|*alma*) DISTRO="fedora" ;;
            *arch*|*manjaro*|*endeavouros*|*garuda*) DISTRO="arch" ;;
            *suse*|*opensuse*) DISTRO="suse" ;;
            *) DISTRO="unknown" ;;
        esac
    fi
}

distro_packages() {
    case "$DISTRO" in
        debian) printf '%s\n' python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo ;;
        fedora) printf '%s\n' python3 python3-gobject gtk3 python3-cairo ;;
        arch)   printf '%s\n' python python-gobject gtk3 python-cairo ;;
        suse)   printf '%s\n' python3 python3-gobject python3-cairo gtk3 ;;
        *)      return 1 ;;
    esac
}

dependencies_ok() {
    python3 - <<'PY' >/dev/null 2>&1
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, GdkPixbuf, Pango
import cairo
PY
}

install_dependencies() {
    if [ "$DISTRO" = "unknown" ]; then
        die "Distribución no reconocida. Instala manualmente: python3, PyGObject, GTK3 y python3-cairo."
    fi

    local packages=()
    mapfile -t packages < <(distro_packages)
    [ "${#packages[@]}" -gt 0 ] || die "No hay paquetes definidos para $DISTRO_NAME"

    local sudo_cmd=()
    if [ "$(id -u)" -ne 0 ]; then
        command -v sudo >/dev/null 2>&1 || die "Necesitas root o sudo para instalar dependencias. Paquetes: ${packages[*]}"
        sudo_cmd=(sudo)
    fi

    log "Instalando dependencias en $DISTRO_NAME..."
    case "$DISTRO" in
        debian)
            "${sudo_cmd[@]}" apt-get update
            "${sudo_cmd[@]}" apt-get install -y "${packages[@]}"
            ;;
        fedora)
            "${sudo_cmd[@]}" dnf install -y "${packages[@]}"
            ;;
        arch)
            "${sudo_cmd[@]}" pacman -S --needed --noconfirm "${packages[@]}"
            ;;
        suse)
            "${sudo_cmd[@]}" zypper --non-interactive install "${packages[@]}"
            ;;
    esac
    log "Dependencias instaladas."
}

shell_quote() {
    printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"
}

desktop_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//\`/\\\`}"
    value="${value//\$/\\\$}"
    value="${value//%/%%}"
    printf '"%s"' "$value"
}

resolve_prefix() {
    if [ "$PREFIX_SET" -eq 0 ]; then
        if [ "$MODE" = "system" ]; then
            PREFIX="/usr"
        else
            PREFIX="${HOME}/.local"
        fi
    fi

    case "$PREFIX" in
        /*) ;;
        *)  PREFIX="$(pwd)/$PREFIX" ;;
    esac

    PREFIX="${PREFIX%/}"
    [ -n "$PREFIX" ] || die "Prefija de instalación no válida"

    BINDIR="$PREFIX/bin"
    LIBDIR="$PREFIX/lib/nawncher"
    APPDIR="$PREFIX/share/applications"
    ICONDIR="$PREFIX/share/icons/hicolor"
    DOCDIR="$PREFIX/share/doc/nawncher"
}

require_root_for_system_install() {
    if [ "$MODE" = "system" ] && [ "$PREFIX_SET" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
        die "Para instalar en /usr ejecuta: sudo $0 --system"
    fi
}

target_home() {
    local user="${SUDO_USER:-}"
    if [ "$MODE" = "system" ] && [ -n "$user" ] && [ "$user" != "root" ]; then
        local home
        home="$(getent passwd "$user" | cut -d: -f6)"
        [ -n "$home" ] && printf '%s\n' "$home" && return 0
    fi
    printf '%s\n' "$HOME"
}

target_user() {
    if [ "$MODE" = "system" ] && [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
        printf '%s\n' "$SUDO_USER"
    fi
}

data_dir_for_user() {
    printf '%s/.nawncher\n' "$(target_home)"
}

create_data_dirs_fallback() {
    local data_dir="$1"
    local owner="${2:-}"

    install -d -m 700 "$data_dir" \
        "$data_dir/games" \
        "$data_dir/covers" \
        "$data_dir/cache" \
        "$data_dir/cache/icons" \
        "$data_dir/logs"

    if [ ! -f "$data_dir/config.json" ]; then
        printf '[]\n' > "$data_dir/config.json"
    fi
    if [ ! -f "$data_dir/stats.json" ]; then
        printf '{}\n' > "$data_dir/stats.json"
    fi
    chmod 600 "$data_dir/config.json" "$data_dir/stats.json" 2>/dev/null || true

    if [ -n "$owner" ]; then
        local group
        group="$(id -gn "$owner" 2>/dev/null || printf '%s' "$owner")"
        chown -R "$owner:$group" "$data_dir" 2>/dev/null || true
    fi
}

migrate_legacy_data() {
    local data_dir="$1"
    [ "$MIGRATE" -eq 1 ] || return 0
    [ -d "$LEGACY_DIR" ] || return 0

    if [ -d "$LEGACY_DIR/covers" ]; then
        mkdir -p "$data_dir/covers"
        cp -a "$LEGACY_DIR/covers/." "$data_dir/covers/" 2>/dev/null || true
    fi
    if [ -d "$LEGACY_DIR/games" ]; then
        mkdir -p "$data_dir/games"
        cp -a "$LEGACY_DIR/games/." "$data_dir/games/" 2>/dev/null || true
    fi

    local result
    result="$(python3 - "$LEGACY_DIR" "$data_dir" <<'PY'
import json
import os
import sys

legacy, data = sys.argv[1], sys.argv[2]

def load(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value
    except Exception:
        return default

def save(path, value):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=4, ensure_ascii=False)
        handle.write("\n")

changed = []
legacy_cfg = load(os.path.join(legacy, "config.json"), [])
target_cfg = load(os.path.join(data, "config.json"), [])
if isinstance(legacy_cfg, list) and legacy_cfg and isinstance(target_cfg, list) and not target_cfg:
    save(os.path.join(data, "config.json"), legacy_cfg)
    changed.append("config")

legacy_stats = load(os.path.join(legacy, "stats.json"), {})
target_stats = load(os.path.join(data, "stats.json"), {})
if isinstance(legacy_stats, dict) and legacy_stats and isinstance(target_stats, dict) and not target_stats:
    save(os.path.join(data, "stats.json"), legacy_stats)
    changed.append("stats")

print(" ".join(changed))
PY
)" || result=""

    if [ -n "$result" ]; then
        log "Datos de la versión portable importados: $result"
        log "Si alguna ruta antigua ya no existe, usa Editar en Nawncher para reseleccionar el .sh."
    fi
}

init_user_data() {
    local data_dir owner
    data_dir="$(data_dir_for_user)"
    owner="$(target_user)"

    if [ -n "$owner" ] && command -v runuser >/dev/null 2>&1; then
        if runuser -u "$owner" -- env HOME="$(target_home)" NAWNCHER_DATA_DIR= "$BINDIR/nawncher" --init-data >/dev/null 2>&1; then
            migrate_legacy_data "$data_dir"
            local group
            group="$(id -gn "$owner" 2>/dev/null || printf '%s' "$owner")"
            chown -R "$owner:$group" "$data_dir" 2>/dev/null || true
            return 0
        fi
    fi

    if [ "$(id -u)" -eq 0 ] && [ -n "$owner" ]; then
        if "$BINDIR/nawncher" --data-dir "$data_dir" --init-data >/dev/null 2>&1; then
            migrate_legacy_data "$data_dir"
            local group
            group="$(id -gn "$owner" 2>/dev/null || printf '%s' "$owner")"
            chown -R "$owner:$group" "$data_dir" 2>/dev/null || true
            return 0
        fi
    fi

    if env NAWNCHER_DATA_DIR= "$BINDIR/nawncher" --init-data >/dev/null 2>&1; then
        migrate_legacy_data "$data_dir"
        return 0
    fi

    warn "No se pudo inicializar ~/.nawncher con Nawncher; se crearán las carpetas básicas."
    create_data_dirs_fallback "$data_dir" "$owner"
    migrate_legacy_data "$data_dir"
}

update_caches() {
    if command -v gtk-update-icon-cache >/dev/null 2>&1; then
        gtk-update-icon-cache -q -t -f "$ICONDIR" 2>/dev/null || true
    fi
    if command -v update-desktop-database >/dev/null 2>&1; then
        update-desktop-database -q "$APPDIR" 2>/dev/null || true
    fi
}

install_files() {
    [ -f "$SRC_FILE" ] || die "Falta el archivo principal: $SRC_FILE"
    resolve_prefix

    install -d -m 755 "$BINDIR" "$LIBDIR" "$APPDIR" "$ICONDIR" "$DOCDIR"
    install -m 644 "$SRC_FILE" "$LIBDIR/nawncher.py"

    {
        printf '#!/bin/sh\n'
        printf 'exec python3 %s "$@"\n' "$(shell_quote "$LIBDIR/nawncher.py")"
    } > "$BINDIR/nawncher"
    chmod 755 "$BINDIR/nawncher"

    local icon size
    for icon in "$ICON_ROOT"/*/apps/nawncher.png; do
        [ -f "$icon" ] || continue
        size="$(basename "$(dirname "$(dirname "$icon")")")"
        install -d -m 755 "$ICONDIR/$size/apps"
        install -m 644 "$icon" "$ICONDIR/$size/apps/nawncher.png"
    done

    local exec_quoted
    exec_quoted="$(desktop_quote "$BINDIR/nawncher")"
    cat > "$APPDIR/nawncher.desktop" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
GenericName=Lanzador de juegos
Comment=Lanzador de juegos para Linux
Exec=$exec_quoted %U
Icon=nawncher
Terminal=false
Categories=Game;
Keywords=games;launcher;juegos;nawncher;
StartupNotify=true
StartupWMClass=Nawncher
EOF
    chmod 644 "$APPDIR/nawncher.desktop"

    if [ -f "$README_FILE" ]; then
        install -m 644 "$README_FILE" "$DOCDIR/README.md"
    fi

    update_caches

    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$APPDIR/nawncher.desktop" >/dev/null 2>&1 || \
            warn "El archivo .desktop generó advertencias de validación (la app seguirá funcionando)."
    fi

    init_user_data

    local data_dir
    data_dir="$(data_dir_for_user)"

    log ""
    log "$APP_NAME $APP_VERSION instalado correctamente."
    log "  Programa: $BINDIR/nawncher"
    log "  Datos:    $data_dir"
    log ""
    log "Ya puedes abrirlo desde el menú de aplicaciones o ejecutando: $BINDIR/nawncher"
}

uninstall_files() {
    resolve_prefix

    if [ "$MODE" = "system" ] && [ "$PREFIX_SET" -eq 0 ] && [ "$(id -u)" -ne 0 ]; then
        die "Para desinstalar de /usr ejecuta: sudo $0 --system --uninstall"
    fi

    rm -f "$BINDIR/nawncher"
    rm -f "$APPDIR/nawncher.desktop"
    rm -rf "$LIBDIR" "$DOCDIR"

    local icon size
    for icon in "$ICON_ROOT"/*/apps/nawncher.png; do
        [ -f "$icon" ] || continue
        size="$(basename "$(dirname "$(dirname "$icon")")")"
        rm -f "$ICONDIR/$size/apps/nawncher.png"
        rmdir "$ICONDIR/$size/apps" 2>/dev/null || true
        rmdir "$ICONDIR/$size" 2>/dev/null || true
    done

    update_caches

    local data_dir
    data_dir="$(data_dir_for_user)"

    if [ "$PURGE" -eq 1 ]; then
        rm -rf "$data_dir"
        log "$APP_NAME desinstalado y datos borrados de $data_dir"
    else
        log "$APP_NAME desinstalado."
        log "Tus datos se conservan en $data_dir"
        log "Para borrarlos también: $0 --uninstall --purge"
    fi
}

main() {
    parse_args "$@"
    detect_distro

    if [ "$ACTION" = "uninstall" ]; then
        uninstall_files
        return 0
    fi

    require_root_for_system_install

    if [ "$DEPENDENCIES" != "no" ]; then
        if dependencies_ok; then
            log "Dependencias comprobadas correctamente."
        elif [ "$DEPENDENCIES" = "yes" ]; then
            install_dependencies
        else
            warn "Faltan dependencias de Python/GTK3 o cairo."
            if [ -t 0 ] && [ -t 1 ]; then
                local answer
                read -r -p "¿Instalarlas ahora con el gestor de $DISTRO_NAME? [s/N] " answer
                case "$answer" in
                    s|S|y|Y) install_dependencies ;;
                    *) warn "Continuando sin instalar dependencias. La app podría no arrancar." ;;
                esac
            else
                warn "Usa --deps para instalarlas automáticamente."
            fi
        fi
    fi

    install_files
}

main "$@"
