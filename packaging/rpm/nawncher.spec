Name:           nawncher
Version:        2.0.0
Release:        1
Summary:        Lanzador de juegos para Linux
License:        Unspecified
URL:            https://github.com/Ynaw-private/Nawncher
Source0:        %{name}-%{version}.tar.gz
BuildArch:      noarch

Requires:       python3
Requires:       python3-gobject
Requires:       gtk3
Requires:       python3-cairo
Recommends:     ffmpeg

%description
Nawncher es un lanzador gráfico de juegos para Linux con lista de juegos,
carátulas, estadísticas de uso y soporte para GIF/WebP/WebM.
Los datos de usuario se guardan en ~/.nawncher.

%prep
%setup -q

%build

%install
rm -rf %{buildroot}
install -d %{buildroot}%{_bindir}
install -d %{buildroot}%{_prefix}/lib/nawncher
install -d %{buildroot}%{_datadir}/applications
install -d %{buildroot}%{_datadir}/icons/hicolor

install -m 644 src/nawncher.py %{buildroot}%{_prefix}/lib/nawncher/nawncher.py
cat > %{buildroot}%{_bindir}/nawncher <<EOF
#!/bin/sh
exec python3 %{_prefix}/lib/nawncher/nawncher.py "\$@"
EOF
chmod 755 %{buildroot}%{_bindir}/nawncher

for size in 512x512 256x256 128x128 64x64 48x48 32x32; do
    install -d %{buildroot}%{_datadir}/icons/hicolor/$size/apps
    install -m 644 data/icons/$size/apps/nawncher.png %{buildroot}%{_datadir}/icons/hicolor/$size/apps/nawncher.png
done

cat > %{buildroot}%{_datadir}/applications/nawncher.desktop <<'EOF'
[Desktop Entry]
Type=Application
Version=1.0
Name=Nawncher
GenericName=Lanzador de juegos
Comment=Lanzador de juegos para Linux
Exec=/usr/bin/nawncher
Icon=nawncher
Terminal=false
Categories=Game;
Keywords=games;launcher;juegos;nawncher;
StartupNotify=true
StartupWMClass=Nawncher
EOF
chmod 644 %{buildroot}%{_datadir}/applications/nawncher.desktop

%post
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q %{_datadir}/applications 2>/dev/null || true
fi

%postun
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q -t -f %{_datadir}/icons/hicolor 2>/dev/null || true
fi
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database -q %{_datadir}/applications 2>/dev/null || true
fi

%files
%{_bindir}/nawncher
%{_prefix}/lib/nawncher/nawncher.py
%{_datadir}/applications/nawncher.desktop
%{_datadir}/icons/hicolor/512x512/apps/nawncher.png
%{_datadir}/icons/hicolor/256x256/apps/nawncher.png
%{_datadir}/icons/hicolor/128x128/apps/nawncher.png
%{_datadir}/icons/hicolor/64x64/apps/nawncher.png
%{_datadir}/icons/hicolor/48x48/apps/nawncher.png
%{_datadir}/icons/hicolor/32x32/apps/nawncher.png
%doc README.md

%changelog
* Sun Nov 01 2026 Nawncher <nawncher@localhost> - 2.0.0-1
- Versión instalable con datos en ~/.nawncher y paquetes para Debian, Fedora y Arch.
