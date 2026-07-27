# MushTato Icon & Splash Assets

Derived from `MushTato_Logo_source.png` (the original combined 1254x1254
composite, kept here only for reference/regeneration -- nothing at
runtime loads it directly).

## Contents

- `icon.png` -- 1024x1024 master icon, real alpha transparency (fixed
  2026-07-26; the original export had an RGBA channel present but every
  pixel fully opaque, which rendered as a hard black square on any
  non-black background -- corrected via a flood-fill from the four
  corners through connected near-black pixels only, so isolated dark
  details inside the artwork itself, like the glasses lenses, were left
  alone).
- `icon/16.png` ... `icon/1024.png` -- the same master pre-rendered at
  each standard size (16/24/32/48/64/128/256/512/1024), for a crisp
  multi-resolution `QIcon` rather than relying on runtime scaling of a
  single image.
- `icon.ico` -- Windows multi-res icon (7 sizes: 16/24/32/48/64/128/256).
- `icon.icns` -- macOS icon bundle.
- `splash.png` -- 830x1207 splash screen art, native resolution (no
  upscaling), black background intentionally baked in (opaque, not
  transparent -- correct for `QSplashScreen`, which needs an opaque
  image).

## Resolution notes

The icon artwork's native source is only 385x385px; everything above
512px (especially `icon/1024.png` and `icon.png`) is upscaled via
Lanczos resampling, not native resolution. Looks clean on screen but
isn't pixel-perfect -- regenerate from a higher-res source if a crisper
master is ever needed.

## Bundling

Referenced by `gui/app.py` (window icon, splash screen),
`gui/tray_icon.py` (tray icon), and `packaging/mushtato.spec` (the
built executable's own icon on Windows/macOS) via
`gui/asset_paths.py`'s `assets_dir()`, which resolves correctly whether
running from source or from a frozen PyInstaller build.
