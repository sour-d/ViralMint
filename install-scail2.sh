#!/bin/bash

BASE=/workspace/runpod-slim/ComfyUI/models

mkdir -p $BASE/checkpoints
mkdir -p $BASE/clip_vision
mkdir -p $BASE/text_encoders
mkdir -p $BASE/vae
mkdir -p $BASE/diffusion_models
mkdir -p $BASE/loras

wget -c -P $BASE/checkpoints \
https://huggingface.co/Comfy-Org/sam3.1/resolve/main/checkpoints/sam3.1_multiplex_fp16.safetensors

wget -c -P $BASE/clip_vision \
https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/clip_vision/clip_vision_h.safetensors

wget -c -P $BASE/text_encoders \
https://huggingface.co/Comfy-Org/Wan_2.1_ComfyUI_repackaged/resolve/main/split_files/text_encoders/umt5_xxl_fp16.safetensors

wget -c -O $BASE/vae/wan_2.1_vae.safetensors \
https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Wan2_1_VAE_bf16.safetensors

wget -c -P $BASE/loras \
https://huggingface.co/Kijai/WanVideo_comfy/resolve/main/Lightx2v/lightx2v_I2V_14B_480p_cfg_step_distill_rank256_bf16.safetensors

wget -c -P $BASE/loras \
https://huggingface.co/Comfy-Org/SCAIL-2/resolve/main/loras/wan2.1_SCAIL_2_DPO_lora_bf16.safetensors

#Full Precision <-- 33 GB
# wget -c -P $BASE/diffusion_models \
# https://huggingface.co/Comfy-Org/SCAIL-2/resolve/main/diffusion_models/wan2.1_14B_SCAIL_2_fp16.safetensors

# FP8 Scaled <-- 17 GB
# wget -c -P $BASE/diffusion_models \
# https://huggingface.co/Comfy-Org/SCAIL-2/resolve/main/diffusion_models/wan2.1_14B_SCAIL_2_fp8_scaled.safetensors

# NVFP4 MXPF8 Mix <-- 11 GB
wget -c -P $BASE/diffusion_models \
https://huggingface.co/Comfy-Org/SCAIL-2/resolve/main/diffusion_models/wan2.1_14B_SCAIL_2_nvfp4_mxpf8_mix.safetensors