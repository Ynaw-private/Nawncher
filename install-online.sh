#!/usr/bin/env bash
# Instalador de una línea para Nawncher.
#
#   curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash -s -- --user
#
# Por defecto instala el paquete nativo del sistema (.deb, .rpm o pacman).
# Con --user instala solo para el usuario actual en ~/.local.
set -euo pipefail

APP_NAME="Nawncher"
APP_ID="nawncher"
APP_VERSION="2.0.0"
PKG_RELEASE="1"

REPO="${NAWNCHER_REPO:-Ynaw-private/Nawncher}"
BRANCH="${NAWNCHER_BRANCH:-main}"
RAW="${NAWNCHER_RAW_BASE:-https://raw.githubusercontent.com/$REPO/$BRANCH}"
ARCHIVE="${NAWNCHER_ARCHIVE_URL:-https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz}"

MODE="system"
DEPS="yes"
DISTRO="unknown"
DISTRO_NAME="Linux"
SUDO=()
TMP=""

usage() {
    cat <<'EOF'
Nawncher - instalador de una línea

Uso:
  curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash
  curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash -s -- --user

Opciones:
  --system            Instala el paquete del sistema (por defecto, usa sudo).
  --user              Instala solo para el usuario actual en ~/.local.
  --deps              Instala dependencias si hacen falta (por defecto).
  --no-deps           No instala dependencias.
  -h, --help          Muestra esta ayuda.
  --version           Muestra la versión.

También puedes cambiar el repositorio con NAWNCHER_REPO=usuario/repo.
EOF
}

log()  { printf '%s\n' "$*"; }
warn() { printf 'Aviso: %s\n' "$*" >&2; }
die()  { printf 'Error: %s\n' "$*" >&2; exit 1; }

cleanup() {
    [ -n "$TMP" ] && rm -rf "$TMP"
}
trap cleanup EXIT

parse_args() {
    while [ "$#" -gt 0 ]; do
        case "$1" in
            --system)  MODE="system"; shift ;;
            --user)    MODE="user"; shift ;;
            --deps)    DEPS="yes"; shift ;;
            --no-deps) DEPS="no"; shift ;;
            -h|--help) usage; exit 0 ;;
            --version) printf '%s %s\n' "$APP_NAME" "$APP_VERSION"; exit 0 ;;
            *)         die "Opción desconocida: $1 (usa --help)" ;;
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
            *debian*|*ubuntu*|*linuxmint*|*pop*)       DISTRO="debian" ;;
            *fedora*|*rhel*|*centos*|*rocky*|*alma*)   DISTRO="fedora" ;;
            *arch*|*manjaro*|*endeavouros*|*garuda*)   DISTRO="arch" ;;
            *)                                         DISTRO="unknown" ;;
        esac
    fi
}

prepare_sudo() {
    [ "$(id -u)" -eq 0 ] && return 0
    command -v sudo >/dev/null 2>&1 ||
        die "Se necesita root para instalar el paquete. Ejecuta el instalador con sudo."
    SUDO=(sudo)
}

fetch() {
    local url="$1" dest="$2"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL --retry 3 --connect-timeout 20 -o "$dest" "$url"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$dest" "$url"
    else
        die "Necesitas curl o wget para descargar Nawncher."
    fi
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    elif command -v shasum >/dev/null 2>&1; then
        shasum -a 256 "$1" | awk '{print $1}'
    else
        return 1
    fi
}

verify_checksum() {
    local file="$1" name expected actual
    name="$(basename "$file")"

    if [ ! -f "$TMP/SHA256SUMS" ]; then
        fetch "$RAW/builds/SHA256SUMS" "$TMP/SHA256SUMS" 2>/dev/null || return 0
    fi

    expected="$(awk -v name="$name" '$2 == name {print $1; exit}' "$TMP/SHA256SUMS")"
    [ -n "$expected" ] || return 0

    actual="$(sha256_of "$file" || true)"
    if [ -n "$actual" ] && [ "$actual" != "$expected" ]; then
        die "La suma SHA256 de $name no coincide. Descarga abortada."
    fi
    log "SHA256 verificado: $name"
}

package_name() {
    case "$DISTRO" in
        debian) printf 'nawncher_%s_all.deb\n' "$APP_VERSION" ;;
        fedora) printf 'nawncher-%s-%s.noarch.rpm\n' "$APP_VERSION" "$PKG_RELEASE" ;;
        arch)   printf 'nawncher-%s-%s-any.pkg.tar.zst\n' "$APP_VERSION" "$PKG_RELEASE" ;;
        *)      return 1 ;;
    esac
}

install_package() {
    local pkg_name pkg_path
    pkg_name="$(package_name)" || return 1
    pkg_path="$TMP/$pkg_name"

    log "Descargando $pkg_name..."
    if ! fetch "$RAW/builds/$pkg_name" "$pkg_path"; then
        warn "No se pudo descargar $pkg_name."
        return 1
    fi
    verify_checksum "$pkg_path"

    case "$DISTRO" in
        debian)
            log "Instalando con apt (Debian/Ubuntu)..."
            "${SUDO[@]}" apt-get install -y "$pkg_path"
            ;;
        fedora)
            log "Instalando con dnf (Fedora/RHEL)..."
            "${SUDO[@]}" dnf install -y "$pkg_path"
            ;;
        arch)
            log "Instalando con pacman (Arch)..."
            "${SUDO[@]}" pacman -S --needed --noconfirm python python-gobject gtk3 python-cairo
            "${SUDO[@]}" pacman -U --noconfirm "$pkg_path"
            ;;
    esac
}

install_from_source() {
    local src_dir
    log "Instalando desde el código fuente..."
    fetch "$ARCHIVE" "$TMP/nawncher-source.tar.gz"
    tar -xzf "$TMP/nawncher-source.tar.gz" -C "$TMP"
    src_dir="$(find "$TMP" -maxdepth 1 -type d \( -name 'Nawncher-*' -o -name 'nawncher-*' \) | head -n 1)"
    [ -n "$src_dir" ] || die "No se pudo extraer el código fuente."

    local deps_flag="--deps"
    [ "$DEPS" = "no" ] && deps_flag="--no-deps"

    if [ "$MODE" = "system" ]; then
        "${SUDO[@]}" bash "$src_dir/install.sh" --system "$deps_flag"
    else
        bash "$src_dir/install.sh" --user "$deps_flag"
    fi
}

main() {
    parse_args "$@"
    detect_distro
    TMP="$(mktemp -d)"

    log "$APP_NAME $APP_VERSION - $DISTRO_NAME"

    if [ "$MODE" = "system" ]; then
        prepare_sudo
        if ! install_package; then
            warn "No hay paquete nativo para esta distribución; se usará el instalador universal."
            install_from_source
        fi
    else
        install_from_source
    fi

    printf '\n%s instalado. Ejecuta "nawncher" o búscalo en el menú de aplicaciones.\n' "$APP_NAME"
    printf 'Datos de usuario: ~/.nawncher\n'
}

main "$@"
