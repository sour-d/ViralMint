#!/usr/bin/env python3
# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
RunPod bootstrap — executed on the GPU pod by ComfyUI-Manager after this repo is
cloned into custom_nodes (viralmint-runpod-bootstrap pack).

1. Merges LTX 2.3 entries into ComfyUI-Manager local model-list.json (whitelist).
2. Downloads missing models with wget/curl into ComfyUI model folders.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

REPO_ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = REPO_ROOT / "backend" / "runpod" / "models_manifest.json"


def _log(msg: str) -> None:
    print(f"[ViralMint bootstrap] {msg}", flush=True)


def find_comfy_root() -> Path:
    env = os.environ.get("COMFYUI_PATH", "").strip()
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    for candidate in (
        Path("/workspace/runpod-slim/ComfyUI"),
        Path("/workspace/ComfyUI"),
    ):
        if candidate.is_dir():
            return candidate
    here = Path(__file__).resolve().parent
    for parent in [here, *here.parents]:
        if (parent / "main.py").is_file() or (parent / "server.py").is_file():
            return parent
    return Path("/workspace/runpod-slim/ComfyUI")


def manager_model_list_path(comfy_root: Path) -> Path | None:
    for name in ("ComfyUI-Manager", "comfyui-manager", "ComfyUI-Manager-main"):
        path = comfy_root / "custom_nodes" / name / "model-list.json"
        if path.is_file():
            return path
    return None


def load_manifest_entries() -> list[dict]:
    if not MANIFEST_PATH.is_file():
        _log(f"manifest not found: {MANIFEST_PATH}")
        return []
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = []
    for m in data.get("models", []):
        entries.append({
            "name": m.get("name") or m["filename"],
            "type": m.get("type") or m.get("folder", "checkpoints"),
            "base": m.get("base") or "LTX-2.3",
            "save_path": m.get("save_path") or "default",
            "filename": m["filename"],
            "url": m["hf_url"],
            "folder": m.get("folder", "checkpoints"),
        })
    return entries


def merge_manager_registry(list_path: Path, entries: list[dict]) -> None:
    if list_path.is_file():
        data = json.loads(list_path.read_text(encoding="utf-8"))
    else:
        data = {"models": []}
    models = data.setdefault("models", [])
    seen = {(x.get("save_path"), x.get("base"), x.get("filename")) for x in models}
    added = 0
    for entry in entries:
        key = (entry["save_path"], entry["base"], entry["filename"])
        if key not in seen:
            models.append({
                "name": entry["name"],
                "type": entry["type"],
                "base": entry["base"],
                "save_path": entry["save_path"],
                "filename": entry["filename"],
                "url": entry["url"],
            })
            seen.add(key)
            added += 1
    list_path.parent.mkdir(parents=True, exist_ok=True)
    list_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    _log(f"merged {added} model(s) into {list_path}")


def hf_url(url: str) -> str:
    token = (
        os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        or os.environ.get("RUNPOD_HF_TOKEN")
        or ""
    ).strip()
    if not token or "huggingface.co" not in url:
        return url
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}token={token}"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".part")
    if partial.exists():
        partial.unlink()
    url = hf_url(url)
    _log(f"downloading {dest.name} ({urlparse(url).netloc})")
    if shutil.which("wget"):
        cmd = ["wget", "-c", "--progress=dot:giga", "-O", str(partial), url]
    elif shutil.which("curl"):
        cmd = ["curl", "-fL", "--retry", "3", "-C", "-", "-o", str(partial), url]
    else:
        raise RuntimeError("Neither wget nor curl found on pod")
    subprocess.run(cmd, check=True)
    partial.rename(dest)
    _log(f"saved {dest} ({dest.stat().st_size // (1024 * 1024)} MiB)")


def download_models(comfy_root: Path, entries: list[dict]) -> None:
    for entry in entries:
        folder = entry["folder"]
        dest = comfy_root / "models" / folder / entry["filename"]
        if dest.is_file() and dest.stat().st_size > 1024:
            _log(f"skip existing {dest.name}")
            continue
        download_file(entry["url"], dest)


def main() -> int:
    _log("starting")
    comfy_root = find_comfy_root()
    _log(f"ComfyUI root: {comfy_root}")
    entries = load_manifest_entries()
    if not entries:
        _log("no models in manifest — nothing to do")
        return 1
    list_path = manager_model_list_path(comfy_root)
    if list_path:
        merge_manager_registry(list_path, entries)
    else:
        _log("ComfyUI-Manager model-list.json not found — skipping registry merge")
    download_models(comfy_root, entries)
    _log("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
