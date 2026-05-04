#!/usr/bin/env python3
"""
RealWings ACF/OBJ Editor for ToLiss A319 / A320 / A321
=======================================================

A unified installer script that edits .acf and .obj files to install
the RealWings wing-replacement mods on any of the three ToLiss Airbus
narrowbodies. Run from the same folder as the *.acf files - i.e. the
ToLiss aircraft root folder.

What it does:
  1. Removes stock wing OBJs from each XP12 ACF (wing[321]L/R.obj,
     wings_glass.obj) and adds the chosen RealWings variant.
  2. Deletes obsolete LIGHT_PARAM blocks from lights_out3XX_XP12.obj
     (the strobes/nav-lights baked into the stock wings).
  3. Deletes the obsolete TRIS blocks from Decals.obj (stock decals
     that referenced the old wing geometry).
  4. (A319 only, when no Carda mod is detected) Deletes obsolete TRIS
     lines from engines.obj.
  5. (When Carda engines are detected) Updates the Carda engine ACF
     coordinates to RealWings values, and deletes the IAE/CFM
     'kit' TRIS line from each Carda CFM/IAE engine OBJ.

Variants available:
  A319 - CEO (Main + Glass + Secondary + Flaps)
  A320 - CEO wingtips, CEO sharklets, NEO
  A321 - CEO wingtips, CEO sharklets, NEO

Only one wing variant can be active at a time (mod limitation: the
RealWings OBJs lack the internal ANIM_hide directives that the stock
single-wing OBJ uses to switch between sharklet/non-sharklet/neo).
Re-run the installer to switch variants.

Usage:
    # Interactive (prompts for aircraft and variant):
    python install_realwings.py --aircraft-dir "/path/to/Airbus A321 (ToLiss)"

    # Fully non-interactive:
    python install_realwings.py --aircraft a321 --variant neo \\
        --frames yes --aircraft-dir "/path/to/Airbus A321 (ToLiss)"
"""

import abc
import argparse
import re
import shutil
import struct
import sys
from dataclasses import dataclass
from pathlib import Path


# ─── Constants ────────────────────────────────────────────────────────────────

# _obj_flags bitfield (per Plane Maker):
#   shadow:    0=none, 8=Prefill, 16=All Views, 24=All Views + High Res
#   lighting:  +1 Inside, +2 Glass(outside)
FLAGS_SHADOW_ALL_VIEWS = 24  # All Views + High Res shadow
FLAGS_LIGHT_INSIDE = 1  # no shadow, inside-light
FLAGS_LIGHT_GLASS_OUTSIDE = 2  # no shadow, glass-outside light

# Wing object placement (per RealWings ReadMe):
#   Main / Flaps / Secondary / Glass:  LONG=72.30 LAT=0.00  VERT=0.40
#   Frames / Lines:                    LONG=60.98 LAT=6.00  VERT=2.06
# ACF axes: x=LAT, y=VERT, z=LONG
WING_X, WING_Y, WING_Z = 0.0, 0.40, 72.30
FRAMES_X, FRAMES_Y, FRAMES_Z = 6.00, 2.06, 60.98

# Carda RealWings-adjusted engine coordinates (per RealWings ReadMe):
#   ceo (CFM56 / V2500):  LONG=21.50 LAT=0.00 VERT=0.80   (was 20.70/0/0.40)
#   neo L (LEAP / PW):    LONG=42.30 LAT=-19.00 VERT=-6.00  (was 41.70/-19/-6.6)
#   neo R (LEAP / PW):    LONG=42.30 LAT= 19.00 VERT=-6.00
CEO_X, CEO_Y, CEO_Z = 0.0, 0.80, 21.50
NEO_L_X, NEO_Y, NEO_Z = -19.0, -6.0, 42.30
NEO_R_X = 19.0

# Particles OBJs whose coordinates must NOT be touched.
_CARDA_PARTICLE_PATTERN = re.compile(r"/particles/", re.IGNORECASE)

# Carda ceo-engine OBJ → 1-based line number where the 'kit' TRIS line lives.
# These line numbers come straight from the RealWings ReadMes.  The
# installer probes the file: if the line at the documented position
# starts with "TRIS", it is deleted; otherwise (file already edited or
# variant mismatch) we fall back to the alternate candidates.
_CARDA_TRIS_TARGETS: dict[str, list[int]] = {
    # CFM56-5B variant for ToLiss A321 / A320
    "CFM56/cfm56_l_engine.obj": [64124, 64123, 63001],  # 5B-321, 5B-319, 5A-319
    "CFM56/cfm56_r_engine.obj": [64122, 64121, 62924],
    "V2500/iae_l_engine.obj": [56010, 56008],  # 321/320, 319
    "V2500/iae_r_engine.obj": [56010, 56008],
}

SEPARATOR_WIDTH = 60


# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class ACFObject:
    """A Misc Object entry to add to the ACF."""

    file_stl: str
    flags: int = 0
    hide_dataref: str = ""
    x: float = 0.0
    y: float = WING_Y
    z: float = WING_Z
    body: int = -1
    gear: int = -1
    wing: int = -1
    phi_ref: float = 0.0
    psi_ref: float = 0.0
    the_ref: float = 0.0
    is_internal: int = 0
    steers_with_gear: int = 0


@dataclass
class WingVariant:
    """A selectable wing configuration (one body + one flaps set)."""

    key: str  # CLI key, e.g. 'neo'
    label: str  # display label
    body_objs: list[str]  # Main / Glass / Secondary OBJ basenames (no folder)
    flaps_obj: str  # Flaps OBJ basename (no folder)


# ─── Aircraft Configuration ──────────────────────────────────────────────────


class AircraftConfig(abc.ABC):
    """Per-aircraft differences for the RealWings installer."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Short display name, e.g. 'A319'."""

    @property
    @abc.abstractmethod
    def realwings_folder(self) -> str:
        """RealWings subfolder under objects/, e.g. 'RealWings321'."""

    @property
    @abc.abstractmethod
    def stock_wing_objs(self) -> list[str]:
        """Stock wing OBJ filenames to remove from the ACF."""

    @property
    @abc.abstractmethod
    def lights_obj(self) -> str:
        """lights_out OBJ filename (relative to objects/)."""

    @property
    @abc.abstractmethod
    def variants(self) -> list[WingVariant]:
        """Available wing variants for this aircraft."""

    @property
    def frames_objs(self) -> tuple[str, str]:
        """(Frames, Lines) OBJ basenames (no folder).  Default suffix=''."""
        return ("Frames.obj", "Lines.obj")

    @property
    def extra_engine_tris_targets(self) -> dict[str, list[int]]:
        """Extra engine.obj TRIS-line deletions when no Carda mod is present."""
        return {}


class A319Config(AircraftConfig):
    """ToLiss A319.  CEO-only.  RealWings319 mod.

    Stock wing OBJs: wingR.obj, wingL.obj, wings_glass.obj  (no '319' suffix).
    Frames/Lines: 'Frames.obj' / 'Lines.obj'.
    A319-only: when Carda is NOT installed, also delete 4 obsolete TRIS lines
               from engines.obj at lines 117685, 117696, 117814, 117827.
    """

    name = "A319"
    realwings_folder = "RealWings319"
    stock_wing_objs = ["wingR.obj", "wingL.obj", "wings_glass.obj"]
    lights_obj = "lights_out319_XP12.obj"

    @property
    def variants(self):
        return [
            WingVariant(
                key="ceo",
                label="CEO (Main + Glass + Secondary + Flaps)",
                body_objs=["Main.obj", "Glass.obj", "Secondary.obj"],
                flaps_obj="Flaps.obj",
            ),
        ]

    @property
    def extra_engine_tris_targets(self):
        return {"engines.obj": [117685, 117696, 117814, 117827]}


class A320Config(AircraftConfig):
    """ToLiss A320 (neo + ceo).  RealWings320 mod (+ RealWings319 for ceo flaps).

    Stock wing OBJs: wingR.obj, wingL.obj, wings_glass.obj  (no '320' suffix).
    Frames/Lines: 'Frames320.obj' / 'Lines320.obj'.

    Variants:
      - neo:           MainNEO + GlassNEO + SecondaryNEO + FlapsNEO
      - ceo-sharklets: MainNEO + GlassNEO + SecondaryNEO + Flaps     (Flaps comes
                                                                     from RealWings319)
      - ceo-wingtips:  Main    + Glass    + Secondary    + Flaps     (Main/Glass/
                                                                     Secondary also
                                                                     from RealWings319)
    """

    name = "A320"
    realwings_folder = "RealWings320"
    stock_wing_objs = ["wingR.obj", "wingL.obj", "wings_glass.obj"]
    lights_obj = "lights_out320_XP12.obj"
    frames_objs = ("Frames320.obj", "Lines320.obj")

    @property
    def variants(self):
        return [
            WingVariant(
                key="neo",
                label="NEO (default)",
                body_objs=["MainNEO.obj", "GlassNEO.obj", "SecondaryNEO.obj"],
                flaps_obj="FlapsNEO.obj",
            ),
            WingVariant(
                key="ceo-sharklets",
                label="CEO with sharklets (needs RealWings319 'Flaps' merged in)",
                body_objs=["MainNEO.obj", "GlassNEO.obj", "SecondaryNEO.obj"],
                flaps_obj="Flaps.obj",
            ),
            WingVariant(
                key="ceo-wingtips",
                label="CEO with wingtips (needs RealWings319 OBJs merged in)",
                body_objs=["Main.obj", "Glass.obj", "Secondary.obj"],
                flaps_obj="Flaps.obj",
            ),
        ]


class A321Config(AircraftConfig):
    """ToLiss A321 (ceo + neo).  RealWings321 mod (CEO + NEO subfolders merged).

    Stock wing OBJs: wing321R.obj, wing321L.obj, wings_glass.obj.
    Frames/Lines: 'Frames321.obj' / 'Lines321.obj'.

    Variants (from the merged 'CEO' + 'NEO' subfolder contents):
      - ceo-wingtips:  Main    + Glass    + Secondary    + Flaps321
      - ceo-sharklets: MainNEO + GlassNEO + SecondaryNEO + Flaps321
      - neo:           MainNEO + GlassNEO + SecondaryNEO + Flaps321NEO
    """

    name = "A321"
    realwings_folder = "RealWings321"
    stock_wing_objs = ["wing321R.obj", "wing321L.obj", "wings_glass.obj"]
    lights_obj = "lights_out321_XP12.obj"
    frames_objs = ("Frames321.obj", "Lines321.obj")

    @property
    def variants(self):
        return [
            WingVariant(
                key="ceo-wingtips",
                label="CEO with wingtips",
                body_objs=["Main.obj", "Glass.obj", "Secondary.obj"],
                flaps_obj="Flaps321.obj",
            ),
            WingVariant(
                key="ceo-sharklets",
                label="CEO with sharklets",
                body_objs=["MainNEO.obj", "GlassNEO.obj", "SecondaryNEO.obj"],
                flaps_obj="Flaps321.obj",
            ),
            WingVariant(
                key="neo",
                label="NEO",
                body_objs=["MainNEO.obj", "GlassNEO.obj", "SecondaryNEO.obj"],
                flaps_obj="Flaps321NEO.obj",
            ),
        ]


AIRCRAFT_CONFIGS: dict[str, type[AircraftConfig]] = {
    "a319": A319Config,
    "a320": A320Config,
    "a321": A321Config,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def format_float32(val: float) -> str:
    """Format a float in X-Plane's single-precision 9-decimal-place style."""
    (unpacked,) = struct.unpack("f", struct.pack("f", val))
    return f"{unpacked:.9f}"


def _backup(filepath: Path, suffix: str = ".bak") -> None:
    bak = filepath.with_suffix(filepath.suffix + suffix)
    if not bak.exists():
        shutil.copy2(filepath, bak)


def _read_lines(filepath: Path) -> list[str]:
    with open(filepath, "r", encoding="utf-8") as f:
        return f.readlines()


def _write_lines(filepath: Path, lines: list[str]) -> None:
    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(lines)


def section(title: str) -> None:
    print(f"\n── {title} " + "─" * max(0, SEPARATOR_WIDTH - len(title) - 4))


# ─── Wing object construction ────────────────────────────────────────────────


def build_realwings_objects(
    config: AircraftConfig,
    variant: WingVariant,
    include_frames: bool,
) -> list[ACFObject]:
    """Build the list of ACF objects to add for the chosen variant."""
    folder = config.realwings_folder

    # Body OBJs:
    #   * Glass / GlassNEO use the Glass-outside lighting flag (no shadow).
    #   * Everything else (Main, Secondary, Flaps) uses All Views shadow.
    objects: list[ACFObject] = []
    for basename in variant.body_objs:
        is_glass = basename.lower().startswith("glass")
        flags = FLAGS_LIGHT_GLASS_OUTSIDE if is_glass else FLAGS_SHADOW_ALL_VIEWS
        objects.append(
            ACFObject(f"{folder}/{basename}", flags, x=WING_X, y=WING_Y, z=WING_Z)
        )

    # Flaps
    objects.append(
        ACFObject(
            f"{folder}/{variant.flaps_obj}",
            FLAGS_SHADOW_ALL_VIEWS,
            x=WING_X,
            y=WING_Y,
            z=WING_Z,
        )
    )

    # Optional Frames + Lines (cabin window frames; inside-light, no shadow)
    if include_frames:
        frames_basename, lines_basename = config.frames_objs
        for basename in (frames_basename, lines_basename):
            objects.append(
                ACFObject(
                    f"{folder}/{basename}",
                    FLAGS_LIGHT_INSIDE,
                    x=FRAMES_X,
                    y=FRAMES_Y,
                    z=FRAMES_Z,
                )
            )

    return objects


def all_known_realwings_filenames(config: AircraftConfig) -> list[str]:
    """All possible RealWings OBJ filenames across every variant for this
    aircraft, plus Frames/Lines.  Used to purge stale entries on re-run."""
    folder = config.realwings_folder
    seen: set[str] = set()
    for variant in config.variants:
        for basename in variant.body_objs:
            seen.add(f"{folder}/{basename}")
        seen.add(f"{folder}/{variant.flaps_obj}")
    for basename in config.frames_objs:
        seen.add(f"{folder}/{basename}")
    return sorted(seen)


# ─── ACF Editor ───────────────────────────────────────────────────────────────


class ACFEditor:
    """Reads, modifies, and writes X-Plane .acf property files."""

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self._header_lines: list[str] = []
        self._properties: dict[str, str] = {}
        self._footer_lines: list[str] = []
        self._read()

    def _read(self) -> None:
        in_props = past_props = False
        for line in _read_lines(self.filepath):
            stripped = line.rstrip("\n\r")
            if stripped.startswith("P "):
                in_props, past_props = True, False
                parts = stripped.split(" ", 2)
                self._properties[parts[1]] = parts[2] if len(parts) > 2 else ""
            elif in_props:
                in_props, past_props = False, True
                self._footer_lines.append(line)
            elif past_props:
                self._footer_lines.append(line)
            else:
                self._header_lines.append(line)

    def save(self, backup: bool = True) -> None:
        if backup:
            _backup(self.filepath)
        with open(self.filepath, "w", encoding="utf-8", newline="\n") as f:
            f.writelines(self._header_lines)
            for key in sorted(self._properties):
                f.write(f"P {key} {self._properties[key]}\n")
            f.writelines(self._footer_lines)

    # ── Queries ────────────────────────────────────────────────────────────

    def get_obja_count(self) -> int:
        return int(self._properties.get("_obja/count", "0"))

    def get_obja_entries(self) -> dict[int, dict[str, str]]:
        entries: dict[int, dict[str, str]] = {}
        for key, value in self._properties.items():
            if key.startswith("_obja/") and key != "_obja/count":
                _, idx_str, *prop_parts = key.split("/")
                entries.setdefault(int(idx_str), {})["/".join(prop_parts)] = value
        return entries

    def has_object(self, filename: str) -> bool:
        return any(
            k.endswith("/_v10_att_file_stl") and v == filename
            for k, v in self._properties.items()
        )

    def is_xp12(self) -> bool:
        """An ACF is XP12 if any object references an *_XP12.obj file."""
        for key, value in self._properties.items():
            if key.endswith("/_v10_att_file_stl") and "_XP12.obj" in value:
                return True
        return False

    def find_carda_engine_objects(self) -> dict[int, str]:
        """Return {obja_idx: file_stl} for every Carda engine OBJ referenced
        in this ACF (excluding particles)."""
        out: dict[int, str] = {}
        for idx, props in self.get_obja_entries().items():
            stl = props.get("_v10_att_file_stl", "")
            if stl.startswith(
                ("CFM56/", "V2500/", "LEAP Engines/", "PW Engines/")
            ) and not _CARDA_PARTICLE_PATTERN.search(stl):
                out[idx] = stl
        return out

    # ── Mutation ───────────────────────────────────────────────────────────

    def remove_and_add_objects(
        self,
        filenames_to_remove: list[str],
        objects_to_add: list[ACFObject],
    ) -> tuple[list[str], list[str]]:
        """Remove specified objects (by filename) and append new ones,
        re-indexing the _obja/* key space."""
        entries = self.get_obja_entries()
        remove_set = set(filenames_to_remove)

        indices_to_remove: set[int] = set()
        removed_names: list[str] = []
        for idx, props in entries.items():
            stl = props.get("_v10_att_file_stl", "")
            if stl in remove_set:
                indices_to_remove.add(idx)
                removed_names.append(stl)

        already_present: list[str] = []
        filtered_add: list[ACFObject] = []
        for obj in objects_to_add:
            if obj.file_stl not in remove_set and self.has_object(obj.file_stl):
                already_present.append(obj.file_stl)
            else:
                filtered_add.append(obj)

        if not indices_to_remove and not filtered_add:
            return removed_names, already_present

        keys_to_delete = [
            k for k in self._properties if k.startswith("_obja/") and k != "_obja/count"
        ]
        for k in keys_to_delete:
            del self._properties[k]

        survivors = [
            props
            for idx, props in sorted(entries.items())
            if idx not in indices_to_remove
        ]
        new_entries = {i: props for i, props in enumerate(survivors)}
        next_idx = len(new_entries)
        for obj in filtered_add:
            new_entries[next_idx] = self._acf_obj_to_props(obj)
            next_idx += 1

        for idx, props in sorted(new_entries.items()):
            for prop_name, value in sorted(props.items()):
                self._properties[f"_obja/{idx}/{prop_name}"] = value
        self._properties["_obja/count"] = str(len(new_entries))

        return removed_names, already_present

    def update_object_coords(self, idx: int, x: float, y: float, z: float) -> bool:
        """Set the x/y/z of a single _obja/<idx> entry; return True if changed."""
        new = {
            "x": format_float32(x),
            "y": format_float32(y),
            "z": format_float32(z),
        }
        keymap = {
            "x": f"_obja/{idx}/_v10_att_x_acf_prt_ref",
            "y": f"_obja/{idx}/_v10_att_y_acf_prt_ref",
            "z": f"_obja/{idx}/_v10_att_z_acf_prt_ref",
        }
        changed = False
        for axis, key in keymap.items():
            if self._properties.get(key) != new[axis]:
                self._properties[key] = new[axis]
                changed = True
        return changed

    @staticmethod
    def _acf_obj_to_props(obj: ACFObject) -> dict[str, str]:
        props: dict[str, str] = {
            "_obj_flags": str(obj.flags),
            "_v10_att_body": str(obj.body),
            "_v10_att_file_stl": obj.file_stl,
            "_v10_att_gear": str(obj.gear),
            "_v10_att_phi_ref": format_float32(obj.phi_ref),
            "_v10_att_psi_ref": format_float32(obj.psi_ref),
            "_v10_att_the_ref": format_float32(obj.the_ref),
            "_v10_att_wing": str(obj.wing),
            "_v10_att_x_acf_prt_ref": format_float32(obj.x),
            "_v10_att_y_acf_prt_ref": format_float32(obj.y),
            "_v10_att_z_acf_prt_ref": format_float32(obj.z),
            "_v10_is_internal": str(obj.is_internal),
            "_v10_steers_with_gear": str(obj.steers_with_gear),
        }
        if obj.hide_dataref:
            props["_obj_hide_dataref"] = obj.hide_dataref
        return props


# ─── OBJ block deletion (content-based) ──────────────────────────────────────


class _ContentDeleter:
    """Base class for content-signature-driven OBJ line deletion.

    Subclasses implement `find_blocks(lines)` to return a list of
    `(start_idx, length)` tuples (0-based) describing the runs to
    delete.  The base class handles backup + adjacent-blank-line sweep
    + writeback, and a `needs_deletion()` helper for idempotency.
    """

    @classmethod
    def find_blocks(cls, lines: list[str]) -> list[tuple[int, int]]:
        raise NotImplementedError

    @classmethod
    def needs_deletion(cls, filepath: Path) -> bool:
        return bool(cls.find_blocks(_read_lines(filepath)))

    @classmethod
    def delete_blocks(cls, filepath: Path, dry_run: bool = False) -> int:
        lines = _read_lines(filepath)
        blocks = cls.find_blocks(lines)
        if not blocks:
            return 0

        # Collect every line index to drop, including adjacent blanks
        to_drop: set[int] = set()
        for start, length in blocks:
            end = start + length
            for k in range(start, end):
                to_drop.add(k)
            if (
                start > 0
                and lines[start - 1].strip() == ""
                and (start - 1) not in to_drop
            ):
                to_drop.add(start - 1)
            if end < len(lines) and lines[end].strip() == "":
                to_drop.add(end)

        if not dry_run:
            _backup(filepath)
            kept = [ln for i, ln in enumerate(lines) if i not in to_drop]
            _write_lines(filepath, kept)

        return len(to_drop)


class LIGHTPARAMDeleter(_ContentDeleter):
    """Deletes the wing-mounted LIGHT_PARAM blocks from lights_out3XX.

    Signature: a run of exactly 4 consecutive `LIGHT_PARAM` lines whose
    immediately preceding non-blank line is an `ANIM_hide` directive
    (i.e. the strobe_bb / strobe_pm / nav_bb / nav_pm group inside an
    `ANIM_hide ... anim/SHARK` wrapper).

    This signature is *content-based*, so it is immune to line-number
    drift caused by other lights mods (e.g. anndresv's Enhanced Lights).
    """

    _RUN_LENGTH = 4

    @classmethod
    def find_blocks(cls, lines: list[str]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        i = 0
        n = len(lines)
        while i < n:
            if not lines[i].lstrip().startswith("LIGHT_PARAM"):
                i += 1
                continue
            # Measure run length
            run = 0
            while i + run < n and lines[i + run].lstrip().startswith("LIGHT_PARAM"):
                run += 1
            if run == cls._RUN_LENGTH:
                # Preceding non-blank line must be ANIM_hide
                j = i - 1
                while j >= 0 and lines[j].strip() == "":
                    j -= 1
                if j >= 0 and lines[j].lstrip().startswith("ANIM_hide"):
                    out.append((i, run))
            i += run
        return out


class DecalsTRISDeleter(_ContentDeleter):
    """Deletes the wing-decal TRIS lines from Decals.obj.

    Signature: every `TRIS` line that occurs *before the first
    `ANIM_hide` directive* in the file.  These are the wing-mounted
    decal triangle batches; everything after the first `ANIM_hide` is
    a fuselage / emergency-exit / etc decal which we must keep.
    """

    @classmethod
    def find_blocks(cls, lines: list[str]) -> list[tuple[int, int]]:
        out: list[tuple[int, int]] = []
        for i, ln in enumerate(lines):
            stripped = ln.lstrip()
            if stripped.startswith("ANIM_hide"):
                break
            if stripped.startswith("TRIS"):
                out.append((i, 1))
        return out


class TRISLineDeleter:
    """Deletes a single TRIS line at one of several candidate line numbers
    (used for Carda engine OBJ 'kit' lines and A319 stock engines.obj)."""

    @staticmethod
    def delete_first_match(
        filepath: Path, candidate_lines: list[int], dry_run: bool = False
    ) -> int:
        """Try each candidate; delete the first line that starts with TRIS.
        Returns the 1-based line number that was deleted, or 0 if none matched."""
        lines = _read_lines(filepath)
        for target in candidate_lines:
            idx = target - 1
            if 0 <= idx < len(lines) and lines[idx].lstrip().startswith("TRIS"):
                if not dry_run:
                    _backup(filepath)
                    del lines[idx]
                    _write_lines(filepath, lines)
                return target
        return 0

    @staticmethod
    def delete_all_at_lines(
        filepath: Path, target_lines: list[int], dry_run: bool = False
    ) -> int:
        """Delete the TRIS line at each of the given 1-based line numbers
        (verifying that line starts with TRIS).  Lines are processed
        bottom-up so line numbers stay valid."""
        lines = _read_lines(filepath)
        deleted = 0
        for target in sorted(target_lines, reverse=True):
            idx = target - 1
            if 0 <= idx < len(lines) and lines[idx].lstrip().startswith("TRIS"):
                del lines[idx]
                deleted += 1
        if deleted and not dry_run:
            _backup(filepath)
            _write_lines(filepath, lines)
        return deleted


# ─── Carda engine OBJ TRIS-line deletion ─────────────────────────────────────


def fix_carda_engine_objs(obj_dir: Path) -> None:
    """For each Carda IAE/CFM engine OBJ, probe and delete the kit TRIS line."""
    for rel_path, candidates in _CARDA_TRIS_TARGETS.items():
        full = obj_dir / rel_path
        if not full.exists():
            continue
        deleted_at = TRISLineDeleter.delete_first_match(full, candidates)
        if deleted_at:
            print(f"  {rel_path}: Deleted TRIS at line {deleted_at}")
        else:
            # Either already done or unrecognised variant - check if any of
            # the candidate lines used to start with TRIS.  Silent OK.
            print(f"  {rel_path}: OK (no kit TRIS line at known positions)")


# ─── Auto-install RealWings source files ─────────────────────────────────────


def auto_install_realwings_sources(
    aircraft_dir: Path, target_folder_name: str, also_pull_from: list[str]
) -> int:
    """If the user has dropped RealWings3XX/ source folder(s) into the
    aircraft base directory, copy any contained files into
    objects/<target_folder_name>/.

    The downloaded mod archives nest the actual asset files at varying
    depths (e.g. RealWings321/CEO/RealWings321/Main.obj or
    RealWings319/RealWings319/Main.obj) — this routine recursively walks
    each given source folder and copies every file whose *parent
    directory* is named like a `RealWingsNNN` folder.

    `target_folder_name` is the destination subfolder under objects/
    (e.g. 'RealWings321').
    `also_pull_from` is a list of additional `RealWingsNNN` source-folder
    names to scan (e.g. for A320 we pull from both RealWings320 and
    RealWings319 to get the CEO files).

    Returns the number of files copied (0 if there was nothing to do).
    """
    sources_to_scan = [target_folder_name] + list(also_pull_from)
    target_dir = aircraft_dir / "objects" / target_folder_name

    pattern = re.compile(r"^RealWings\d{3}$", re.IGNORECASE)
    n_copied = 0
    n_skipped = 0
    scanned_any = False

    for src_name in sources_to_scan:
        src_root = aircraft_dir / src_name
        if not src_root.is_dir():
            continue
        scanned_any = True
        for path in src_root.rglob("*"):
            if not path.is_file():
                continue
            # Only copy files whose immediate parent is a RealWingsNNN folder
            if not pattern.match(path.parent.name):
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            dest = target_dir / path.name
            if dest.exists() and dest.stat().st_size == path.stat().st_size:
                n_skipped += 1
                continue
            shutil.copy2(path, dest)
            n_copied += 1

    if scanned_any:
        print(
            f"  Source folder(s) found at aircraft base dir; "
            f"copied {n_copied} new file(s), {n_skipped} already up to date."
        )
    return n_copied


# ─── Prompts ──────────────────────────────────────────────────────────────────


def ask_yes_no(prompt: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    while True:
        choice = input(prompt + suffix).strip().lower()
        if not choice:
            return default
        if choice in ("y", "yes"):
            return True
        if choice in ("n", "no"):
            return False
        print("Please enter 'y' or 'n'.")


def ask_choice(prompt: str, options: list[tuple[str, str]]) -> str:
    """Ask the user to pick one of (key, label) options.  Returns the key."""
    print(prompt)
    for n, (_key, label) in enumerate(options, start=1):
        print(f"  {n} - {label}")
    valid = {str(n): key for n, (key, _l) in enumerate(options, start=1)}
    while True:
        raw = input(f"\nEnter 1-{len(options)}: ").strip()
        if raw in valid:
            return valid[raw]
        print(f"  Invalid choice. Please enter 1-{len(options)}.")


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="RealWings ACF/OBJ editor for ToLiss A319 / A320 / A321"
    )
    parser.add_argument(
        "--aircraft-dir",
        type=Path,
        default=Path.cwd(),
        help="Path to the ToLiss aircraft folder (default: current directory)",
    )
    parser.add_argument(
        "--aircraft",
        choices=list(AIRCRAFT_CONFIGS),
        default=None,
        help="Aircraft type (skips interactive prompt)",
    )
    parser.add_argument(
        "--variant",
        default=None,
        help="Wing variant key, e.g. ceo / ceo-wingtips / ceo-sharklets / neo "
        "(skips interactive prompt)",
    )
    parser.add_argument(
        "--frames",
        choices=["yes", "no"],
        default=None,
        help="Install RealWings cabin window frames (yes/no, skips prompt)",
    )
    args = parser.parse_args()
    aircraft_dir: Path = args.aircraft_dir.resolve()

    print("=" * SEPARATOR_WIDTH)
    print(" RealWings Mod - ACF/OBJ Editor v1.0r1")
    print("=" * SEPARATOR_WIDTH)

    # ── Aircraft selection ──
    if args.aircraft is not None:
        aircraft_key = args.aircraft
    else:
        aircraft_key = ask_choice(
            "\nWhich aircraft are you installing for?",
            [("a319", "ToLiss A319"), ("a320", "ToLiss A320"), ("a321", "ToLiss A321")],
        )

    config = AIRCRAFT_CONFIGS[aircraft_key]()
    print(f"\nAircraft: {config.name}")

    # ── Variant selection ──
    variants = config.variants
    variant_map = {v.key: v for v in variants}
    if args.variant is not None:
        if args.variant not in variant_map:
            print(
                f"\nERROR: Variant '{args.variant}' not valid for {config.name}.  "
                f"Choices: {', '.join(variant_map)}"
            )
            sys.exit(1)
        chosen_variant = variant_map[args.variant]
    elif len(variants) == 1:
        chosen_variant = variants[0]
    else:
        key = ask_choice(
            "\nWhich wing variant do you want?",
            [(v.key, v.label) for v in variants],
        )
        chosen_variant = variant_map[key]
    print(f"Variant: {chosen_variant.label}")

    # ── Frames? ──
    if args.frames is not None:
        install_frames = args.frames == "yes"
    else:
        install_frames = ask_yes_no(
            "\nInstall the RealWings cabin window frames? (recommended)",
            True,
        )
    print(f"Window frames: {'yes' if install_frames else 'no'}")

    # ── Validation ──
    acf_files = sorted(aircraft_dir.glob("*.acf"))
    if not acf_files:
        print(f"\nERROR: No .acf files found in {aircraft_dir}")
        print(f"Run this script from the ToLiss {config.name} aircraft folder,")
        print("or use --aircraft-dir to specify the path.")
        sys.exit(1)

    obj_dir = aircraft_dir / "objects"
    realwings_dir = obj_dir / config.realwings_folder

    # ── Auto-install: copy from any RealWings3XX/ folders the user
    # has dropped into the aircraft base directory ──
    # A320 ceo variants need RealWings319 files merged in too.
    extra_sources = ["RealWings319"] if config.name == "A320" else []
    section("Source File Auto-Install")
    auto_install_realwings_sources(aircraft_dir, config.realwings_folder, extra_sources)

    if not realwings_dir.is_dir():
        print(
            f"\nERROR: {config.realwings_folder}/ not found under "
            f"{obj_dir}.\nDrop the RealWings mod's '{config.realwings_folder}' "
            f"folder into either the aircraft base directory or its objects/ "
            f"folder first."
        )
        sys.exit(1)

    # Sanity-check the chosen variant's OBJ files exist on disk.
    needed = list(chosen_variant.body_objs) + [chosen_variant.flaps_obj]
    if install_frames:
        needed += list(config.frames_objs)
    missing = [f for f in needed if not (realwings_dir / f).exists()]
    if missing:
        print(
            f"\nERROR: The following OBJs are missing from {realwings_dir}:\n  "
            + "\n  ".join(missing)
        )
        if config.name == "A320" and chosen_variant.key.startswith("ceo"):
            print(
                "\nThe A320 CEO variants need files merged in from the "
                "RealWings319 mod.  See the readme."
            )
        if config.name == "A321":
            print(
                "\nThe A321 needs the CEO and NEO sub-folders of the "
                "RealWings321 mod merged into objects/RealWings321/.  See the readme."
            )
        sys.exit(1)

    print(f"\nAircraft folder: {aircraft_dir}")
    print(f"Found {len(acf_files)} ACF file(s): {', '.join(f.name for f in acf_files)}")

    realwings_objects = build_realwings_objects(config, chosen_variant, install_frames)
    all_known = all_known_realwings_filenames(config)
    active_filenames = {o.file_stl for o in realwings_objects}

    # ── Step 1: ACF edits ──
    section("ACF File Editing (XP12 ACFs only)")

    edited_any_xp12 = False
    carda_present_in_any_acf = False

    for acf_path in acf_files:
        editor = ACFEditor(acf_path)
        if not editor.is_xp12():
            print(f"\n  {acf_path.name}: skipped (not an XP12 ACF)")
            continue
        edited_any_xp12 = True
        print(f"\n  {acf_path.name}:")

        # Detect Carda
        carda_objs = editor.find_carda_engine_objects()
        if carda_objs:
            carda_present_in_any_acf = True

        # Wing object swap (always purge all known RealWings filenames so
        # switching variant on a re-run leaves no stale entries).
        removed, _already = editor.remove_and_add_objects(
            filenames_to_remove=config.stock_wing_objs + all_known,
            objects_to_add=realwings_objects,
        )
        stock_removed = [n for n in removed if n in config.stock_wing_objs]
        rw_refreshed = [n for n in removed if n in active_filenames]
        stale_removed = [
            n for n in removed if n in all_known and n not in active_filenames
        ]
        if stock_removed:
            print(f"    Removed stock wings: {', '.join(stock_removed)}")
        if stale_removed:
            print(
                f"    Cleaned up {len(stale_removed)} stale RealWings object(s) "
                "from previous install"
            )
        if rw_refreshed:
            print(f"    Refreshed {len(rw_refreshed)} existing RealWings object(s)")
        else:
            print(f"    Added {len(realwings_objects)} RealWings object(s)")

        # Update Carda engine coordinates (if present)
        if carda_objs:
            n_changed = 0
            for idx, stl in carda_objs.items():
                if stl.startswith(("CFM56/", "V2500/")):
                    if editor.update_object_coords(idx, CEO_X, CEO_Y, CEO_Z):
                        n_changed += 1
                elif stl.startswith(("LEAP Engines/", "PW Engines/")):
                    if "_l_" in stl.lower() or stl.endswith(
                        ("_L_Engine.obj", "_N1_L.obj")
                    ):
                        x = NEO_L_X
                    elif "_r_" in stl.lower() or stl.endswith(
                        ("_R_Engine.obj", "_N1_R.obj")
                    ):
                        x = NEO_R_X
                    else:
                        # Unknown - leave alone.
                        continue
                    if editor.update_object_coords(idx, x, NEO_Y, NEO_Z):
                        n_changed += 1
            print(
                f"    Carda detected: updated {n_changed} engine object "
                f"coord(s) (RealWings positions)"
            )

        print(f"    Total object count: {editor.get_obja_count()}")
        editor.save(backup=True)
        print(f"    Saved (backup: {acf_path.name}.bak)")

    if not edited_any_xp12:
        print(
            "\n  WARNING: no XP12 ACFs found.  RealWings is XP12-only - nothing to do."
        )
        return

    # ── Step 2: lights_out OBJ edits ──
    section("Lights OBJ Edits (LIGHT_PARAM blocks)")
    lights_path = obj_dir / config.lights_obj
    if not lights_path.exists():
        print(f"  {config.lights_obj}: not found (skipped)")
    elif not LIGHTPARAMDeleter.needs_deletion(lights_path):
        print(f"  {config.lights_obj}: OK (already cleaned up)")
    else:
        n = LIGHTPARAMDeleter.delete_blocks(lights_path)
        print(f"  {config.lights_obj}: deleted {n} line(s)")

    # ── Step 3: Decals OBJ edits ──
    section("Decals OBJ Edits (TRIS blocks)")
    # The mod readme says 'decals' but on disk the file is named 'Decals.obj'.
    # Try both casings to accommodate either.
    for decals_name in ("Decals.obj", "decals.obj"):
        decals_path = obj_dir / decals_name
        if decals_path.exists():
            break
    if not decals_path.exists():
        print("  Decals.obj: not found (skipped)")
    elif not DecalsTRISDeleter.needs_deletion(decals_path):
        print(f"  {decals_path.name}: OK (already cleaned up)")
    else:
        n = DecalsTRISDeleter.delete_blocks(decals_path)
        print(f"  {decals_path.name}: deleted {n} line(s)")

    # ── Step 4: A319 stock engines.obj (only if no Carda) ──
    if config.extra_engine_tris_targets and not carda_present_in_any_acf:
        section("Stock engines.obj TRIS Line Deletions (no Carda detected)")
        for rel, target_lines in config.extra_engine_tris_targets.items():
            engines_path = obj_dir / rel
            if not engines_path.exists():
                print(f"  {rel}: not found (skipped)")
                continue
            n = TRISLineDeleter.delete_all_at_lines(engines_path, target_lines)
            if n:
                print(f"  {rel}: deleted {n} TRIS line(s)")
            else:
                print(f"  {rel}: OK (already cleaned up)")

    # ── Step 5: Carda engine OBJ kit-TRIS deletions ──
    if carda_present_in_any_acf:
        section("Carda Engine OBJ TRIS Line Deletions")
        fix_carda_engine_objs(obj_dir)

    print("\n" + "=" * SEPARATOR_WIDTH)
    print(" Done!")
    print("=" * SEPARATOR_WIDTH)


if __name__ == "__main__":
    main()
