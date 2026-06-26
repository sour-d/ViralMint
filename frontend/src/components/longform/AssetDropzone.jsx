import { useState } from "react"
import {
  Box, Typography, Button, Stack, IconButton, TextField, Chip, Paper,
} from "@mui/material"
import CloudUploadIcon from "@mui/icons-material/CloudUpload"
import CloseIcon from "@mui/icons-material/Close"
import VideocamIcon from "@mui/icons-material/Videocam"
import ImageIcon from "@mui/icons-material/Image"
import http from "../../api/http"
import useAppStore from "../../store/appStore"

function mediaSrc(url) {
  if (!url) return ""
  if (url.startsWith("http") || url.startsWith("blob:")) return url
  const base = http.defaults.baseURL || ""
  return base ? `${base.replace(/\/$/, "")}${url.startsWith("/") ? url : `/${url}`}` : url
}

const VIDEO_EXTS = [".mp4", ".mov", ".webm", ".mkv"]

export default function AssetDropzone({ assets, onChange }) {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [uploading, setUploading] = useState(false)

  const uploadOne = async (file) => {
    const ext = (file.name.match(/\.[^.]+$/) || [""])[0].toLowerCase()
    const isVideo = VIDEO_EXTS.includes(ext) || file.type.startsWith("video/")
    const endpoint = isVideo ? "/api/media/upload-video" : "/api/media/upload"
    const fd = new FormData()
    fd.append("file", file)
    const res = await http.post(endpoint, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    })
    return {
      url: res.data.url,
      kind: isVideo ? "video" : "image",
      caption: "",
      name: file.name,
    }
  }

  const handleFiles = async (e) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    e.target.value = ""
    setUploading(true)
    try {
      const uploaded = []
      for (const f of files) {
        uploaded.push(await uploadOne(f))
      }
      onChange([...assets, ...uploaded])
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Upload failed", "error")
    } finally {
      setUploading(false)
    }
  }

  const removeAsset = (idx) => {
    onChange(assets.filter((_, i) => i !== idx))
  }

  const updateCaption = (idx, caption) => {
    onChange(assets.map((a, i) => (i === idx ? { ...a, caption } : a)))
  }

  return (
    <Box>
      <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", mb: 0.5, display: "block" }}>
        Images & videos (screenshots, B-roll, photos)
      </Typography>
      <Button
        variant="outlined"
        startIcon={<CloudUploadIcon />}
        component="label"
        disabled={uploading}
        sx={{ mb: 1.5 }}
      >
        {uploading ? "Uploading…" : "Add assets"}
        <input type="file" hidden multiple accept="image/*,video/*,.mp4,.mov,.webm" onChange={handleFiles} />
      </Button>
      <Stack spacing={1}>
        {assets.map((a, idx) => (
          <Paper key={`${a.url}-${idx}`} variant="outlined" sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={1.5} alignItems="flex-start">
              {a.kind === "video" ? (
                <Box
                  component="video"
                  src={mediaSrc(a.url)}
                  muted
                  sx={{ width: 80, height: 56, objectFit: "cover", borderRadius: 1, bgcolor: "grey.900" }}
                />
              ) : (
                <Box
                  component="img"
                  src={mediaSrc(a.url)}
                  alt=""
                  sx={{ width: 80, height: 56, objectFit: "cover", borderRadius: 1 }}
                />
              )}
              <Box sx={{ flex: 1 }}>
                <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                  {a.kind === "video" ? <VideocamIcon fontSize="small" /> : <ImageIcon fontSize="small" />}
                  <Typography variant="caption" sx={{ wordBreak: "break-all" }}>{a.name || a.url.split("/").pop()}</Typography>
                  <Chip label={a.kind} size="small" sx={{ ml: "auto" }} />
                </Stack>
                <TextField
                  size="small"
                  fullWidth
                  placeholder="Optional caption"
                  value={a.caption || ""}
                  onChange={(e) => updateCaption(idx, e.target.value)}
                />
              </Box>
              <IconButton size="small" onClick={() => removeAsset(idx)} aria-label="Remove">
                <CloseIcon fontSize="small" />
              </IconButton>
            </Stack>
          </Paper>
        ))}
      </Stack>
    </Box>
  )
}
