# Nawncher 2.0.0

Lanzador de juegos para Linux con interfaz GTK3, carátulas, estadísticas y soporte
para imágenes animadas (GIF/WebP) y miniatura de vídeos WebM.

Esta versión **ya no es portable**: la aplicación se instala en el sistema o en
`~/.local`, y los datos de usuario viven siempre en `~/.nawncher`.

## Instalación en una línea

```bash
curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash
```

El instalador detecta tu distribución y usa el paquete nativo:

| Distribución | Paquete | Comando que usa |
|---|---|---|
| Debian / Ubuntu / Mint | `.deb` | `apt-get install` |
| Fedora / RHEL / Rocky / Alma | `.rpm` | `dnf install` |
| Arch / Manjaro / EndeavourOS | `.pkg.tar.zst` | `pacman -U` |

Si no hay paquete para tu distribución, cae automáticamente al instalador
universal desde el código fuente.

### Solo para tu usuario (sin instalar en el sistema)

```bash
curl -fsSL https://raw.githubusercontent.com/Ynaw-private/Nawncher/main/install-online.sh | bash -s -- --user
```

Instala en `~/.local` y no necesita sudo para los archivos de la app.

## Paquetes listos para instalar

Los paquetes generados están en la carpeta **`~/builds`** de tu home y también
en `builds/` del repositorio:

```
~/builds/
├── nawncher_2.0.0_all.deb              # Debian / Ubuntu
├── nawncher-2.0.0-1.noarch.rpm         # Fedora / RHEL
├── nawncher-2.0.0-1-any.pkg.tar.zst    # Arch / Manjaro
├── nawncher-2.0.0.tar.gz               # Código fuente
└── SHA256SUMS                          # Comprobación de integridad
```

Instalación manual:

```bash
# Debian / Ubuntu
sudo apt install ./nawncher_2.0.0_all.deb

# Fedora / RHEL
sudo dnf install ./nawncher-2.0.0-1.noarch.rpm

# Arch / Manjaro
sudo pacman -U ./nawncher-2.0.0-1-any.pkg.tar.zst
```

## Qué contiene el proyecto

```
Nawncher/
├── install.sh              # Instalador universal (Debian/Fedora/Arch/openSUSE)
├── install-online.sh       # Instalador de una línea desde GitHub
├── build-packages.sh       # Genera .deb, .rpm y paquete de Arch en ~/builds
├── Makefile
├── src/nawncher.py         # Aplicación GTK3
├── data/
│   ├── nawncher.desktop.in
│   └── icons/              # Iconos 32, 48, 64, 128, 256 y 512 px
├── packaging/
│   ├── rpm/nawncher.spec
│   └── arch/PKGBUILD
└── builds/                 # Paquetes publicados para el instalador online
```

`legacy/` contiene la configuración de la antigua versión portable para migrar
los juegos. Es local y **no se publica** en GitHub porque puede contener rutas
personales.

## Instalación desde el código fuente

### Solo para tu usuario (recomendado, sin sudo)

```bash
cd Nawncher
./install.sh --user
```

Instala en `~/.local`:

- `~/.local/bin/nawncher`
- `~/.local/lib/nawncher/nawncher.py`
- `~/.local/share/applications/nawncher.desktop`
- `~/.local/share/icons/hicolor/.../apps/nawncher.png`

Y crea los datos en `~/.nawncher`.

Si faltan dependencias, el instalador te preguntará si quiere instalarlas. También
puedes forzarlo:

```bash
./install.sh --user --deps
```

### Para todo el sistema

```bash
cd Nawncher
sudo ./install.sh --system --deps
```

Instala en `/usr` y el lanzador queda en `/usr/bin/nawncher`.

### Abrir la app

Desde el menú de aplicaciones busca **Nawncher**, o ejecuta:

```bash
nawncher
```

## Dónde están los datos

Todo lo necesario está en `~/.nawncher`:

```
~/.nawncher/
├── config.json     # Lista de juegos
├── stats.json      # Veces que se ha lanzado cada juego
├── games/          # Carpeta recomendada para tus scripts .sh
├── covers/         # Carpeta recomendada para carátulas
├── cache/icons/    # Icono redondeado generado automáticamente
└── logs/           # Reservado para diagnósticos
```

La app crea esta carpeta automáticamente en el primer arranque. Si quieres usar
otra ubicación (por ejemplo para pruebas), puedes hacer:

```bash
nawncher --data-dir /ruta/alternativa
# o
NAWNCHER_DATA_DIR=/ruta/alternativa nawncher
```

Desde el menú de la propia app puedes abrir `~/.nawncher` con
**Abrir carpeta de datos**.

## Añadir juegos

1. Abre Nawncher.
2. Pulsa **+ Añadir**.
3. Selecciona el archivo `.sh` del juego.
4. Escribe el nombre y, si quieres, selecciona una carátula.

Puedes guardar los juegos donde quieras. Si los pones dentro de
`~/.nawncher/games/`, la ruta se guardará relativa a `~/.nawncher` y será más
fácil de mantener. Si están fuera, se guardará la ruta absoluta.

### Recuperar los juegos de la versión portable

`legacy/config.json` contiene la lista de la versión portable anterior. El
instalador la importa automáticamente si `~/.nawncher/config.json` está vacío.
Las rutas antiguas pueden dejar de existir; en ese caso abre **Editar** en cada
juego y vuelve a seleccionar el `.sh` con **Buscar**.

Si prefieres no importar nada:

```bash
./install.sh --user --no-migrate
```

## Dependencias por distribución

El instalador las detecta y ofrece instalarlas. Estas son las equivalentes:

| Distribución | Paquetes |
|---|---|
| Debian/Ubuntu | `python3 python3-gi python3-gi-cairo gir1.2-gtk-3.0 python3-cairo` |
| Fedora/RHEL | `python3 python3-gobject gtk3 python3-cairo` |
| Arch/Manjaro | `python python-gobject gtk3 python-cairo` |
| openSUSE | `python3 python3-gobject python3-cairo gtk3` |

Opcional:

- `ffmpeg`: mostrar la primera imagen de carátulas `.webm`.

Las dependencias ya están declaradas dentro de cada paquete (`.deb`, `.rpm` y
Arch), así que el gestor de paquetes las instala solo.

## Generar los paquetes

```bash
cd Nawncher
make dist
# o directamente:
./build-packages.sh
```

Los artefactos se crean en **`~/builds`**. También puedes cambiar la carpeta:

```bash
NAWNCHER_OUTPUT_DIR=/otra/ruta ./build-packages.sh
```

- `nawncher_2.0.0_all.deb` — se genera con `ar` y `tar` aunque no tengas
  `dpkg-deb`.
- `nawncher-2.0.0-1.noarch.rpm` — si tienes `rpmbuild` (`rpm-build` en Fedora,
  `rpm` en Debian, `rpm-tools` en Arch). En Fedora, si falta, el script descarga
  `rpm-build` sin root y lo usa automáticamente.
- `nawncher-2.0.0-1-any.pkg.tar.zst` — se genera con `tar` y `zstd` aunque no
  tengas `makepkg`.

### Arch con PKGBUILD

```bash
cp ~/builds/nawncher-2.0.0.tar.gz packaging/arch/
cd packaging/arch
makepkg -si
```

## Publicar en GitHub

El repositorio es `https://github.com/Ynaw-private/Nawncher`.

```bash
git add -A
git commit -m "Nawncher 2.0.0 instalable con paquetes y one-liner"
git push origin main
```

Después de publicar, el one-liner funciona con los paquetes de `builds/`.
Para que el instalador online use una rama distinta:

```bash
NAWNCHER_BRANCH=main curl -fsSL ... | bash
```

## Desinstalar

```bash
# Instalación de usuario
./install.sh --user --uninstall

# Instalación del sistema
sudo ./install.sh --system --uninstall
```

Los datos de `~/.nawncher` se conservan. Para borrarlos también:

```bash
./install.sh --user --uninstall --purge
```

## Comprobar que todo está bien

```bash
make check
nawncher --version
nawncher --init-data
```

`--init-data` crea `~/.nawncher` y muestra su ruta sin abrir la interfaz.

## Notas

- Los juegos que ya tengas instalados no se tocan. La app solo guarda sus rutas.
- El icono se puede personalizar dejando un `icon.png` o `icon.jpg` en
  `~/.nawncher`; Nawncher generará la versión redondeada en `~/.nawncher/cache/icons`.
- El archivo `.desktop` se instala con el nombre `nawncher.desktop` y usa
  `StartupWMClass=Nawncher` para que el dock de GNOME/KDE asocie bien la ventana.
