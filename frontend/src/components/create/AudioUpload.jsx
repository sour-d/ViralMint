import { useState } from "react"
import { Box, Typography, Button, Stack, IconButton } from "@mui/material"
import CloudUploadIcon from "@mui/icons-material/CloudUpload"
import CloseIcon from "@mui/icons-material/Close"
import AudiotrackIcon from "@mui/icons-material/Audiotrack"
import http from "../../api/http"
import useAppStore from "../../store/appStore"

export default function AudioUpload({ label, value, onChange, onRemove }) {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [uploading, setUploading] = useState(false)

  const handleFile = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    e.target.value = ""
    setUploading(true)
    try {
      const fd = new FormData()
      fd.append("file", file)
      const res = await http.post("/api/media/upload-audio", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      onChange(res.data.url)
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Audio upload failed", "error")
      onChange(null)
    } finally {
      setUploading(false)
    }
  }

  if (value) {
    const name = value.split("/").pop()
    return (
      <Box>
        <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", mb: 0.5, display: "block" }}>
          {label}
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ p: 1.5, border: 1, borderColor: "divider", borderRadius: 2 }}>
          <AudiotrackIcon color="primary" />
          <Typography variant="body2" sx={{ flex: 1, wordBreak: "break-all" }}>{name}</Typography>
          <IconButton size="small" onClick={onRemove}><CloseIcon fontSize="small" /></IconButton>
        </Stack>
        <Button size="small" onClick={onRemove} sx={{ mt: 0.5 }}>Remove & re-upload</Button>
      </Box>
    )
  }

  return (
    <Box>
      <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary", mb: 0.5, display: "block" }}>
        {label}
      </Typography>
      <Button
        size="small"
        variant="outlined"
        startIcon={<CloudUploadIcon />}
        component="label"
        disabled={uploading}
      >
        {uploading ? "Uploading…" : "Upload audio"}
        <input type="file" hidden accept="audio/*,.mp3,.wav,.m4a,.ogg,.flac,.aac" onChange={handleFile} />
      </Button>
    </Box>
  )
}
