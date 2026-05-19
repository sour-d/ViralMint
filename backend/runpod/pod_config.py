# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""
Hardcoded RunPod GPU Pod settings for ViralMint ComfyUI.

Matches RunPod console deploy:
  ComfyUI template (cw3nka7d08), runpod/comfyui:latest,
  1x RTX 3090, Community Cloud, 50 GB container + 200 GB volume @ /workspace.
"""

POD_NAME = "video generation"
IMAGE_NAME = "runpod/comfyui:latest"
TEMPLATE_ID = "cw3nka7d08"

# Community Cloud — RTX 3090 on-demand (~$0.22/hr GPU in console)
GPU_TYPE_IDS = ["NVIDIA GeForce RTX 3090"]
GPU_COUNT = 1
CLOUD_TYPE = "COMMUNITY"
SUPPORT_PUBLIC_IP = True

CONTAINER_DISK_GB = 50
VOLUME_GB = 200
VOLUME_MOUNT_PATH = "/workspace"

PORTS = ["8188/http", "22/tcp", "8080/http"]
COMFY_PORT = 8188
