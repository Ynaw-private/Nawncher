#!/usr/bin/env bash
# Construye los paquetes de Nawncher para Debian, Fedora y Arch.
set -euo pipefail

APP_NAME="Nawncher"
APP_ID="nawncher"
VERSION="2.0.0"
RELEASE="1"

SELF_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Por defecto los paquetes van a ~/builds (se puede cambiar con NAWNCHER_OUTPUT_DIR).
DIST_DIR="${NAWNCHER_OUTPUT_DIR:-$HOME/builds}"
BUILD_DIR="$SELF_DIR/build"
TOOLS_DIR="$SELF_DIR/.build-tools"

log()  { printf '%s\n' "$*"; }
warn() { printf 'Aviso: %s\n' "$*" >&2; }

desktop_quote() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    value="${value//\`/\\\`}"
    value="${value//\$/\\\$}"
    value="${value//%/%%}"
    printf '"%s"' "$value"
}

populate_stage() {
    local stage="$1"
    local icon size

    install -d -m 755 \
        "$stage/usr/bin" \
        "$stage/usr/lib/nawncher" \
        "$stage/usr/share/applications" \
        "$stage/usr/share/doc/nawncher" \
        "$stage/usr/share/icons/hicolor"

    install -m 644 "$SELF_DIR/src/nawncher.py" "$stage/usr/lib/nawncher/nawncher.py"

    cat > "$stage/usr/bin/nawncher" <<'EOF'
#!/bin/sh
exec python3 /usr/lib/nawncher/nawncher.py "$@"
EOF
    chmod 755 "$stage/usr/bin/nawncher"

    for icon in "$SELF_DIR"/data/icons/*/apps/nawncher.png; do
        [ -f "$icon" ] || continue
        size="$(basename "$(dirname "$(dirname "$icon")")")"
        install -d -m 755 "$stage/usr/share/icons/hicolor/$size/apps"
        install -m 644 "$icon" "$stage/usr/share/icons/hicolor/$size/apps/nawncher.png"
    done

    local exec_quoted
    exec_quoted="$(desktop_quote "/usr/bin/nawncher")"
    cat > "$stage/usr/share/applications/nawncher.desktop" <<EOF
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
    chmod 644 "$stage/usr/share/applications/nawncher.desktop"

    if [ -f "$SELF_DIR/README.md" ]; then
        install -m 644 "$SELF_DIR/README.md" "$stage/usr/share/doc/nawncher/README.md"
    fi
}

make_source_tarball() {
    local tmp
    tmp="$(mktemp -d)"
    local root="$tmp/$APP_ID-$VERSION"
    mkdir -p "$root"

    cp -a \
        "$SELF_DIR/src" \
        "$SELF_DIR/data" \
        "$SELF_DIR/packaging" \
        "$SELF_DIR/install.sh" \
        "$SELF_DIR/build-packages.sh" \
        "$SELF_DIR/Makefile" \
        "$SELF_DIR/README.md" \
        "$root/"

    # legacy/ guarda rutas y estadísticas personales: no se publica ni se empaqueta.
    find "$root" -type d -name '__pycache__' -prune -exec rm -rf {} +
    find "$root" -type f -name '*.pyc' -delete

    tar -C "$tmp" -czf "$DIST_DIR/$APP_ID-$VERSION.tar.gz" "$APP_ID-$VERSION"
    rm -rf "$tmp"
    log "Creado $DIST_DIR/$APP_ID-$VERSION.tar.gz"
}

build_deb() {
    if ! command -v ar >/dev/null 2>&1; then
        warn "No se encontró 'ar'; se omite el paquete .deb."
        return 0
    fi
    if ! command -v tar >/dev/null 2>&1; then
        warn "No se encontró 'tar'; se omite el paquete .deb."
        return 0
    fi

    local stage tmp
    stage="$(mktemp -d)"
    tmp="$(mktemp -d)"
    populate_stage "$stage"

    local debian="$stage/DEBIAN"
    mkdir -p "$debian"
    local installed_size
    installed_size="$(du -sk "$stage" | cut -f1)"

    cat > "$debian/control" <<EOF
Package: $APP_ID
Version: $VERSION
Section: games
Priority: optional
Architecture: all
Depends: python3, python3-gi, python3-gi-cairo, gir1.2-gtk-3.0, python3-cairo
Recommends: ffmpeg
Maintainer: Nawncher <nawncher@localhost>
Installed-Size: $installed_size
Description: Lanzador de juegos para Linux
 Nawncher es un lanzador gráfico de juegos con lista, carátulas y estadísticas.
 Los datos de usuario se guardan en ~/.nawncher.
EOF

    cat > "$debian/postinst" <<'EOF'
#!/bin/sh
set -e
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q /usr/share/applications 2>/dev/null || true
fi
exit 0
EOF
    cp "$debian/postinst" "$debian/postrm"
    chmod 755 "$debian/postinst" "$debian/postrm"

    (
        cd "$stage"
        find . -path ./DEBIAN -prune -o -type f -print0 |
            while IFS= read -r -d '' file; do
                relative="${file#./}"
                md5sum "$relative"
            done > DEBIAN/md5sums
    )

    if command -v dpkg-deb >/dev/null 2>&1; then
        dpkg-deb --build --root-owner-group "$stage" "$DIST_DIR/${APP_ID}_${VERSION}_all.deb" >/dev/null
    else
        tar -C "$debian" -czf "$tmp/control.tar.gz" control postinst postrm md5sums
        tar -C "$stage" --exclude=./DEBIAN -czf "$tmp/data.tar.gz" .
        printf '2.0\n' > "$tmp/debian-binary"
        (
            cd "$tmp"
            ar rcs "$DIST_DIR/${APP_ID}_${VERSION}_all.deb" debian-binary control.tar.gz data.tar.gz
        )
    fi

    rm -rf "$stage" "$tmp"
    log "Creado $DIST_DIR/${APP_ID}_${VERSION}_all.deb"
}

prepare_rpmbuild() {
    if command -v rpmbuild >/dev/null 2>&1; then
        RPMBUILD_CMD=(rpmbuild)
        return 0
    fi

    if [ -x "$TOOLS_DIR/usr/bin/rpmbuild" ]; then
        RPMBUILD_CMD=("$TOOLS_DIR/usr/bin/rpmbuild")
        return 0
    fi

    # En Fedora se puede usar rpmbuild sin root extrayendo el paquete rpm-build.
    if command -v dnf >/dev/null 2>&1 &&
       command -v rpm2cpio >/dev/null 2>&1 &&
       command -v cpio >/dev/null 2>&1; then
        local download_dir pkg
        download_dir="$(mktemp -d)"
        if dnf download --destdir "$download_dir" rpm-build >/dev/null 2>&1; then
            pkg="$(find "$download_dir" -maxdepth 1 -name 'rpm-build-*.rpm' | head -n 1)"
            if [ -n "$pkg" ]; then
                mkdir -p "$TOOLS_DIR"
                if rpm2cpio "$pkg" | (cd "$TOOLS_DIR" && cpio -idm --quiet) &&
                   [ -x "$TOOLS_DIR/usr/bin/rpmbuild" ]; then
                    RPMBUILD_CMD=("$TOOLS_DIR/usr/bin/rpmbuild")
                    rm -rf "$download_dir"
                    return 0
                fi
            fi
        fi
        rm -rf "$download_dir"
    fi

    return 1
}

build_rpm() {
    if ! prepare_rpmbuild; then
        warn "No se encontró 'rpmbuild' y no se pudo descargar rpm-build. Se omite el .rpm."
        warn "Instala rpm-build (Fedora), rpm (Debian) o rpm-tools (Arch) y vuelve a ejecutar."
        return 0
    fi

    local top
    top="$(mktemp -d)"
    mkdir -p "$top"/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cp "$DIST_DIR/$APP_ID-$VERSION.tar.gz" "$top/SOURCES/"
    cp "$SELF_DIR/packaging/rpm/nawncher.spec" "$top/SPECS/nawncher.spec"

    local defines=(--define "_topdir $top")
    if [ "${RPMBUILD_CMD[0]}" != "rpmbuild" ]; then
        defines+=(
            --define "__rpmuncompress $TOOLS_DIR/usr/lib/rpm/rpmuncompress"
            --define "__check_files $TOOLS_DIR/usr/lib/rpm/check-files"
            --define "__os_install_post %{nil}"
        )
    fi

    "${RPMBUILD_CMD[@]}" "${defines[@]}" -bb "$top/SPECS/nawncher.spec" >/dev/null
    find "$top/RPMS" -name '*.rpm' -exec cp {} "$DIST_DIR/" \;
    rm -rf "$top"
    log "Creado paquete .rpm en $DIST_DIR"
}

build_arch() {
    if ! command -v zstd >/dev/null 2>&1; then
        warn "No se encontró 'zstd'; se omite el paquete de Arch."
        return 0
    fi

    local stage size builddate
    stage="$(mktemp -d)"
    populate_stage "$stage"
    size="$(du -sb "$stage" | cut -f1)"
    builddate="$(date +%s)"

    cat > "$stage/.PKGINFO" <<EOF
# Generated by Nawncher build-packages.sh
pkgname = $APP_ID
pkgbase = $APP_ID
pkgver = $VERSION-$RELEASE
pkgdesc = Lanzador de juegos para Linux
url = https://github.com/Ynaw-private/Nawncher
builddate = $builddate
packager = Nawncher
size = $size
arch = any
license = custom
depend = python
depend = python-gobject
depend = gtk3
depend = python-cairo
optdepend = ffmpeg: miniaturas de carátulas .webm
EOF

    cat > "$stage/.INSTALL" <<'EOF'
post_install() {
    gtk-update-icon-cache -q -t -f usr/share/icons/hicolor 2>/dev/null || true
    update-desktop-database -q usr/share/applications 2>/dev/null || true
}
post_upgrade() {
    post_install "$@"
}
post_remove() {
    gtk-update-icon-cache -q -t -f usr/share/icons/hicolor 2>/dev/null || true
    update-desktop-database -q usr/share/applications 2>/dev/null || true
}
EOF
    chmod 644 "$stage/.PKGINFO" "$stage/.INSTALL"

    # .MTREE permite que pacman -Qkk verifique los archivos del paquete.
    python3 - "$stage" <<'PY'
import gzip
import hashlib
import os
import stat
import sys

stage = sys.argv[1]
entries = []
for root, dirs, files in os.walk(stage):
    dirs.sort()
    files.sort()
    for name in dirs:
        path = os.path.join(root, name)
        relative = "./" + os.path.relpath(path, stage)
        entries.append((relative, path, "dir"))
    for name in files:
        path = os.path.join(root, name)
        relative = "./" + os.path.relpath(path, stage)
        if relative == "./.MTREE":
            continue
        entries.append((relative, path, "file"))

entries.sort(key=lambda item: item[0])
lines = ["#mtree", "/set type=file uid=0 gid=0 mode=644"]
for relative, path, kind in entries:
    info = os.lstat(path)
    mode = stat.S_IMODE(info.st_mode)
    timestamp = int(info.st_mtime)
    if kind == "dir":
        lines.append("%s time=%d mode=%o type=dir" % (relative, timestamp, mode))
    else:
        with open(path, "rb") as handle:
            data = handle.read()
        lines.append(
            "%s time=%d mode=%o size=%d md5digest=%s sha256digest=%s"
            % (
                relative,
                timestamp,
                mode,
                info.st_size,
                hashlib.md5(data).hexdigest(),
                hashlib.sha256(data).hexdigest(),
            )
        )

with open(os.path.join(stage, ".MTREE"), "wb") as handle:
    handle.write(gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0))
PY

    tar -C "$stage" --zstd -cf "$DIST_DIR/${APP_ID}-${VERSION}-${RELEASE}-any.pkg.tar.zst" .
    rm -rf "$stage"
    log "Creado $DIST_DIR/${APP_ID}-${VERSION}-${RELEASE}-any.pkg.tar.zst"
}

main() {
    [ -f "$SELF_DIR/src/nawncher.py" ] || {
        printf 'Error: falta src/nawncher.py\n' >&2
        exit 1
    }

    rm -rf "$BUILD_DIR"
    mkdir -p "$DIST_DIR"
    rm -f \
        "$DIST_DIR/$APP_ID-$VERSION.tar.gz" \
        "$DIST_DIR/${APP_ID}_${VERSION}_all.deb" \
        "$DIST_DIR/${APP_ID}-${VERSION}-${RELEASE}-any.pkg.tar.zst" \
        "$DIST_DIR"/nawncher-*.rpm \
        "$DIST_DIR/SHA256SUMS"

    make_source_tarball
    build_deb
    build_rpm
    build_arch

    (
        cd "$DIST_DIR"
        sha256sum nawncher-*.tar.gz nawncher_*.deb nawncher-*.rpm nawncher-*.pkg.tar.zst 2>/dev/null > SHA256SUMS || true
    )

    printf '\nPaquetes generados en %s:\n' "$DIST_DIR"
    ls -lh "$DIST_DIR"
}

main "$@"
