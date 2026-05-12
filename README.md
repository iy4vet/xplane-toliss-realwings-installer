# RealWings Installer for ToLiss A319 / A320 / A321 v1.1r1

Installer script for the [RealWings319](https://forums.x-plane.org/files/file/99042-realwings319-wing-replacement-mod-for-toliss-a319/), [RealWings320](https://forums.x-plane.org/files/file/99352-realwings320-wing-replacement-mod-for-toliss-a320neo/) and [RealWings321](https://forums.x-plane.org/files/file/99442-realwings321-wing-replacement-mod-for-toliss-a321neoceo) wing-replacement mods by [GeoBuilds](https://forums.x-plane.org/profile/962966-geobuilds/) and [Durantula2405](https://forums.x-plane.org/profile/843947-durantula2405/). Handles all `.acf` and `.obj` edits so you don't have to do them by hand. If the [Carda engine mod](https://github.com/iy4vet/xplane-toliss-carda-installer) is installed, auto-detects and fixes those coordinates too.

## What the installer does

**TL;DR: Everything. You only need to copy the RealWings folder in and run this script.** Specifically, for each XP12 `.acf` it:

1. **Replaces the stock wing OBJs** with RealWings replacements at the correct positions, shadow modes, and lighting flags.
2. **Cleans up dangling geometry** - removes the obsolete `LIGHT_PARAM` blocks from `lights_out3XX_XP12.obj`, stale `TRIS` blocks from `Decals.obj`, and (A319 without Carda) stale `TRIS` from `engines.obj`.
3. **Updates Carda engine coordinates** (if detected) to RealWings-adjusted positions, and strips the 'kit' `TRIS` line from each CFM/IAE engine OBJ.

Backups (`.bak`) are created automatically. Non-XP12 ACF files are skipped.

### Wing variants

Only one variant can be active at a time. Re-run the installer to switch.

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

Just unzip the RealWings download into your aircraft folder. The installer finds `RealWings3XX/` source folders at the aircraft base dir and copies them into `objects/RealWings3XX/` automatically.

A few things to note per aircraft:

- **A319** - no special steps; drop the zip contents in.
- **A320** - the mod ships NEO geometry only. For CEO variants, also drop in the **RealWings319** mod; the installer merges both into `objects/RealWings320/`. Skip this if you only want NEO.
- **A321** - the zip nests assets under `CEO/` and `NEO/` subfolders; just drop the whole `RealWings321/` folder in and the installer handles the merge.

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

The installer will ask which aircraft (A319 / A320 / A321), which variant, and whether to install the optional cabin window frames.

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

## Credits and Licensing

This project is licensed under the GNU GPL v3.

Any contributions (features or bugfixes) are very welcome. [Here's the project GitHub](https://github.com/iy4vet/xplane-toliss-realwings-installer).

Feel free to message me on Discord - my username is `iy4vet`. I'm also present in the X-Plane Community and Official servers.

A huge thank-you to:

- [GeoBuilds](https://forums.x-plane.org/profile/962966-geobuilds/) and [Durantula2405](https://forums.x-plane.org/profile/843947-durantula2405/) - RealWings mod authors.
- [@alexvor20](https://github.com/alexvor20) - the original [auto-installers](https://github.com/alexvor20/xplane-toliss-realwings-installer) for RealWings.

## Changelog

- **1.1r1** - fix: re-detect Carda after wing swap (was missed on re-runs)
- **1.0r1** - Initial release. Unified A319/A320/A321 installer with auto Carda detection, auto-copy of source folders, and content-based OBJ edits (no hard-coded line numbers).
