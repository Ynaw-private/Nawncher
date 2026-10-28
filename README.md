# Nawncher

Lanzador 100% portable para Linux. Todo autocontenido en una carpeta. Usa `zenity` para la interfaz.

## Estructura

```
Nawncher/
├── Nawncher.sh        # Punto de entrada (ejecutable)
└── .data/
    ├── config.json    # Configuración de juegos
    ├── launcher/
    │   └── nawncher.sh
    ├── games/         # Coloca aquí tus archivos .sh
    ├── covers/        # Carátulas (png/jpg/gif)
    └── assets/
```

## Cómo usarlo

1. Ejecuta `./Nawncher.sh` desde la carpeta `Nawncher/`
2. Añade tus juegos en `.data/config.json`
3. Coloca tus `.sh` en `.data/games/` (o usa rutas absolutas)
4. Coloca carátulas en `.data/covers/` y añádelas a la config

## Cambiar el logo

Sustituye `.data/Icon.jpg` por otro JPG (también vale `.data/icon.jpg`). Al abrir el launcher se genera automáticamente la versión con esquinas redondeadas en `.data/.icon-cache/` y se actualiza el icono de la app.

## Configuración

Edita `.data/config.json`:

```json
[
  {
    "name": "Mi Juego",
    "script": ".data/games/mi-juego.sh",
    "cover": ".data/covers/mi-juego.png"
  }
]
```

- `name` - Nombre que aparece en la lista
- `script` - Ruta al `.sh` (relativa a `Nawncher/` o absoluta)
- `cover` - Ruta de la carátula (relativa o absoluta). Opcional

## Características

- **100% portable** - Mueve toda la carpeta donde quieras, funciona con rutas relativas
- **Lista a la izquierda** - Selecciona el juego desde el listado
- **Carátula + botón JUGAR** - Vista previa con carátula a la derecha
- **Pantalla de carga** - Muestra "Lanzando..." mientras arranca
- **Todo en .data/** - El lanzador y recursos ocultos en `.data/`
- **Offline** - Sin dependencias de internet

## Requisitos

- `bash`
- `zenity` (normalmente ya viene en muchas distros)
- `python3` (opcional, pero recomendado para leer `config.json` correctamente)

## Truco

Si tienes `yad` instalado, la vista con carátula queda un poco mejor. No es obligatorio.
