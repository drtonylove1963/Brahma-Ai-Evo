"""
memory/persona_profiles.py - Saved assistant personas (name + voice + personality).

A persona is what the assistant calls itself, which Gemini voice it speaks
with, and optional personality notes added to its instructions. Personas are
saved by name in BrahmaAI/config/personas.json; activating one writes those
values into the live identity and voice settings and bumps `persona_rev`, which
makes the running voice session reconnect as the new persona.
"""

from __future__ import annotations

import json
import threading
from typing import Dict, List, Optional

from core.user_paths import get_user_data_dir
from memory import config_manager

PERSONAS_FILE = get_user_data_dir() / "config" / "personas.json"
_LOCK = threading.Lock()


def _identity():
    from core.identity import identity
    return identity


def _read() -> dict:
    try:
        with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("profiles"), dict):
            return data
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[Personas] Could not read {PERSONAS_FILE}: {e}")
    return _seed()


def _write(data: dict) -> None:
    PERSONAS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PERSONAS_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
    tmp.replace(PERSONAS_FILE)


def _seed() -> dict:
    """First run: save whatever persona is live now as the first profile."""
    ident = _identity()
    name = (ident.get_assistant_name() or "Brahma").strip() or "Brahma"
    data = {
        "active": name,
        "profiles": {
            name: {
                "name": name,
                "voice": config_manager.get_voice_name(),
                "instructions": ident.get_custom_instructions() or "",
            }
        },
    }
    try:
        _write(data)
    except Exception as e:
        print(f"[Personas] Could not seed {PERSONAS_FILE}: {e}")
    return data


def _find(profiles: dict, name: str) -> Optional[str]:
    """Profile key matching `name`, ignoring case and surrounding spaces."""
    want = (name or "").strip().lower()
    for key in profiles:
        if key.lower() == want:
            return key
    return None


def list_profiles() -> List[dict]:
    with _LOCK:
        data = _read()
    return [dict(p) for _k, p in sorted(data["profiles"].items(), key=lambda kv: kv[0].lower())]


def get_profile(name: str) -> Optional[dict]:
    with _LOCK:
        profiles = _read()["profiles"]
        key = _find(profiles, name)
        return dict(profiles[key]) if key else None


def get_active_name() -> str:
    with _LOCK:
        data = _read()
    active = data.get("active") or ""
    return active if active in data["profiles"] else ""


def save_profile(name: str, voice: str, instructions: str = "") -> dict:
    """Create or overwrite a profile. Does not activate it."""
    name = (name or "").strip()
    if not name:
        raise ValueError("A persona needs a name.")
    if voice not in config_manager.VOICE_OPTIONS:
        raise ValueError(f"Unknown voice {voice!r}.")
    profile = {"name": name, "voice": voice, "instructions": (instructions or "").strip()}
    with _LOCK:
        data = _read()
        old = _find(data["profiles"], name)
        if old and old != name:            # renamed only by case
            data["profiles"].pop(old)
            if data.get("active") == old:
                data["active"] = name
        data["profiles"][name] = profile
        _write(data)
    return dict(profile)


def delete_profile(name: str) -> bool:
    with _LOCK:
        data = _read()
        key = _find(data["profiles"], name)
        if not key:
            return False
        if len(data["profiles"]) == 1:
            raise ValueError("Keep at least one persona.")
        data["profiles"].pop(key)
        if data.get("active") == key:
            data["active"] = ""
        _write(data)
    return True


def activate(name: str) -> dict:
    """Make a saved persona live: name, voice and instructions, then reconnect."""
    with _LOCK:
        data = _read()
        key = _find(data["profiles"], name)
        if not key:
            raise KeyError(name)
        profile = dict(data["profiles"][key])
        data["active"] = key
        _write(data)

    ident = _identity()
    ident.set_assistant_name(profile["name"])
    ident.set_custom_instructions(profile.get("instructions", ""))
    config_manager.set_voice_name(profile["voice"])
    # The voice may be unchanged, so bump a revision the session watches too.
    config_manager.set_setting("persona_rev", int(config_manager.get_setting("persona_rev", 0) or 0) + 1)
    return profile


def get_persona_rev() -> int:
    try:
        return int(config_manager.get_setting("persona_rev", 0) or 0)
    except Exception:
        return 0
