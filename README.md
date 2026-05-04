# RealWings Installer for ToLiss A319 / A320 / A321 v1.0r1

Installer script for the [RealWings319](https://forums.x-plane.org/files/file/99042-realwings319-wing-replacement-mod-for-toliss-a319/), [RealWings320](https://forums.x-plane.org/files/file/99352-realwings320-wing-replacement-mod-for-toliss-a320neo/) and [RealWings321](https://forums.x-plane.org/files/file/99442-realwings321-wing-replacement-mod-for-toliss-a321neoceo) wing-replacement mods by [GeoBuilds](https://forums.x-plane.org/profile/962966-geobuilds/) and [Durantula2405](https://forums.x-plane.org/profile/843947-durantula2405/). Handles all `.acf` and `.obj` edits so you don't have to do them by hand.

If you also use the Carda engine mods (CFM56, V2500, LEAP-1A, PW1100G), this installer **auto-detects them and fixes them too** - no need to redo the engine coordinates or run a separate Carda-RealWings fork.

## What the installer does

**TL;DR: Everything. You only need to copy the RealWings folder in and run this script.** Specifically, for each XP12 `.acf` it will:

1. **Remove the stock wing OBJs** (`wing[321]L.obj`, `wing[321]R.obj`, `wings_glass.obj`) and add the RealWings replacement objects with the correct positions, shadow modes, and lighting flags.
2. **Update Carda engine coordinates** (if the Carda mod is detected) to the RealWings-adjusted positions:
   - ceo (CFM56 / V2500): `LONG=21.50 LAT=0.00 VERT=0.80`
   - neo (LEAP / PW): `LONG=42.30 LAT=±19.00 VERT=-6.00`

It will then edit the OBJ files:

1. **Delete the obsolete `LIGHT_PARAM` blocks** from `lights_out3XX_XP12.obj` (the strobes/nav lights baked into the stock wing geometry that would otherwise be left dangling).
2. **Delete the obsolete `TRIS` blocks** from `Decals.obj` (the stock decals that referenced the old wing geometry).
3. **(A319 only, no Carda)** Delete the obsolete `TRIS` lines from `engines.obj`.
4. **(Carda detected)** Delete the 'kit' `TRIS` line from each Carda CFM/IAE engine OBJ (`cfm56_l_engine.obj`, `cfm56_r_engine.obj`, `iae_l_engine.obj`, `iae_r_engine.obj`).

Backups (`.bak`) are created automatically before any file is modified. ACF files that aren't XP12 are skipped (RealWings is XP12-only).

### Wing variants

Only one wing variant can be active at a time - this is a mod limitation. The stock single-wing OBJ contains internal `ANIM_hide` directives (`anim/SHARK`, `anim/NEO`) that switch between sharklet/non-sharklet/neo geometry; the separate RealWings OBJs do not, and `_obj_hide_dataref` only supports a single condition. Just re-run the installer to switch variants.

| Aircraft | Variants |
| -------- | -------- |
| A319     | CEO (only option) |
| A320     | NEO, CEO with sharklets, CEO with wingtips |
| A321     | CEO with wingtips, CEO with sharklets, NEO |

## Step 1 - Download the RealWings mods

Download the mods for your aircraft:

| Mod | Link |
| --- | ---- |
| RealWings319 | <https://forums.x-plane.org/files/file/99042-realwings319-wing-replacement-mod-for-toliss-a319/> |
| RealWings320 | <https://forums.x-plane.org/files/file/99352-realwings320-wing-replacement-mod-for-toliss-a320neo/> |
| RealWings321 | <https://forums.x-plane.org/files/file/99442-realwings321-wing-replacement-mod-for-toliss-a321neoceo/> |

## Step 2 - Copy the RealWings folder into your aircraft

The installer can pull the RealWings asset files **either** from `objects/RealWings3XX/` (the final destination) **or** from a `RealWings3XX/` source folder dropped at the aircraft base directory (next to the `.acf` files). If a source folder is found at the base directory, the installer copies every file from any nested `RealWings3XX/` subfolder into `objects/RealWings3XX/` automatically before running the rest of the install. So in the simplest case, just unzip the RealWings download into your aircraft folder.

If you want to wire it up by hand, the OBJs need to live under `objects/RealWings3XX/`:

### A319

Drop the `RealWings319/` folder from the mod zip into your aircraft folder (or place the contents directly under `objects/RealWings319/`).

```txt
Airbus A319 (ToLiss)/objects/RealWings319/
├── Main.obj
├── Glass.obj
├── Secondary.obj
├── Flaps.obj
├── Frames.obj
├── Lines.obj
└── … (textures)
```

### A320

The A320 mod ships only NEO geometry. To unlock the CEO variants, also download the **RealWings319** mod and drop it in too - the installer will merge files from both `RealWings319/` and `RealWings320/` source folders into `objects/RealWings320/`.

```txt
Airbus A320 (ToLiss)/objects/RealWings320/
├── MainNEO.obj  GlassNEO.obj  SecondaryNEO.obj  FlapsNEO.obj   ← from RealWings320
├── Main.obj     Glass.obj     Secondary.obj     Flaps.obj      ← from RealWings319 (CEO variants only)
├── Frames320.obj  Lines320.obj
└── … (textures)
```

If you only want the NEO variant, the RealWings319 files are not needed.

### A321

The A321 zip nests the assets under `RealWings321/CEO/RealWings321/` and `RealWings321/NEO/RealWings321/`. Just drop the whole `RealWings321/` folder at the aircraft base dir; the installer walks the tree and merges both subfolders into `objects/RealWings321/` for you.

```txt
Airbus A321 (ToLiss)/objects/RealWings321/
├── Main.obj  Glass.obj  Secondary.obj  Flaps321.obj             ← CEO body + CEO flaps
├── MainNEO.obj  GlassNEO.obj  SecondaryNEO.obj                  ← shared sharklet body
├── Flaps321NEO.obj                                              ← NEO flaps
├── Frames321.obj  Lines321.obj
└── … (textures)
```

### Liveries

If a livery ships its own RealWings textures, copy that livery's `objects/RealWings3XX/` folder into the matching livery folder under your aircraft.

## Step 3 - Run the installer

### Option A: Pre-built binary (no Python needed)

Download the binary for your OS from the [Releases](https://github.com/iy4vet/xplane-toliss-realwings-installer/releases/latest/) page:

| Platform | Binary |
| -------- | ------ |
| Windows x64 | `install-realwings-windows-x64.exe` |
| Windows ARM64 | `install-realwings-windows-arm64.exe` |
| macOS Apple Silicon | `install-realwings-macos-arm64` |
| macOS Intel | `install-realwings-macos-x64` |
| Linux x64 | `install-realwings-linux-x64` |
| Linux ARM64 | `install-realwings-linux-arm64` |

Place the binary inside your aircraft folder. On Windows, just double-click. On macOS/Linux you may need to make it executable first:

```bash
# Example (A321, Linux):
cd "/path/to/Airbus A321 (ToLiss)"
chmod +x install-realwings-linux-x64
./install-realwings-linux-x64
```

The installer will ask which aircraft (A319 / A320 / A321), which variant, and whether to install the optional cabin window frames. It works alongside other lights/decals mods (e.g. anndresv's [Enhanced Lights](https://forums.x-plane.org/files/file/69851-enhanced-lights-for-toliss-a319320321330340/)) without any extra steps or interventions.

### Option B: Run with Python

Requires Python 3.10+. No external dependencies.

```bash
cd "/path/to/Airbus A321 (ToLiss)"
python install_realwings.py
```

For fully non-interactive use (e.g. scripting):

```bash
python install_realwings.py \
    --aircraft a321 \
    --variant ceo-sharklets \
    --frames yes \
    --aircraft-dir "/path/to/Airbus A321 (ToLiss)"
```

Variant keys: `ceo` (A319 only), `ceo-wingtips`, `ceo-sharklets`, `neo`.

## Switching variants

Just re-run the installer with a different variant choice. Stale RealWings objects from the previous variant are detected and removed automatically; the wing position, lights and decals edits are idempotent.

## Carda compatibility

If the Carda engine mod is already installed, the installer detects it (by the presence of `CFM56/`, `V2500/`, `LEAP Engines/` or `PW Engines/` OBJs in the ACF) and:

- Updates the engine ACF coordinates to RealWings-adjusted positions (ceo: `21.50/0/0.80`; neo L: `42.30/-19.00/-6.00`; neo R: `42.30/19.00/-6.00`). Particles are left untouched.
- Deletes the 'kit' `TRIS` line from each CFM/IAE engine OBJ (the L and R engines for both engine families). The line numbers vary by aircraft / engine sub-variant; the installer probes the documented candidates.

If you install Carda *after* running the RealWings installer, just re-run RealWings to apply the Carda fixes.

## Credits and Licensing

This project is licensed under the GNU GPL v3.

Any contributions (features or bugfixes) are very welcome. [Here's the project GitHub](https://github.com/iy4vet/xplane-toliss-realwings-installer).

Feel free to message me on Discord - my username is `iy4vet`. I'm also present in the X-Plane Community and Official servers.

A huge thank-you to:

- [GeoBuilds](https://forums.x-plane.org/profile/962966-geobuilds/) and [Durantula2405](https://forums.x-plane.org/profile/843947-durantula2405/) - RealWings mod authors.
- [@alexvor20](https://github.com/alexvor20) - the original [auto-installers](https://github.com/alexvor20/xplane-toliss-realwings-installer) for RealWings, the structure of which informed this one.

## Changelog

- **1.0r1** - Initial release. Unified A319/A320/A321 installer with auto Carda detection, auto-copy of source folders dropped at the aircraft base dir, and content-based OBJ edits (no hard-coded line numbers; works with other lights/decals mods).
