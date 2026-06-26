import { useMemo, useState } from "react"
import {
  Box, Typography, Button, Stack, Paper, Chip, MenuItem, TextField, CircularProgress,
  FormControl, InputLabel, Select,
} from "@mui/material"
import RefreshIcon from "@mui/icons-material/Refresh"
import http from "../../api/http"

function mediaSrc(url) {
  if (!url) return ""
  if (url.startsWith("http") || url.startsWith("blob:")) return url
  const base = http.defaults.baseURL || ""
  return base ? `${base.replace(/\/$/, "")}${url.startsWith("/") ? url : `/${url}`}` : url
}

function fmtTime(s) {
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${String(sec).padStart(2, "0")}`
}

const SCENE_TYPES = ["kenburns", "user_image", "screenshot", "user_video", "stock", "ltx"]

function PreviewBox({ label, children, minHeight = 120 }) {
  return (
    <Box sx={{ flex: 1, minWidth: 0 }}>
      <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
        {label}
      </Typography>
      <Box
        sx={{
          mt: 0.5, borderRadius: 1, border: 1, borderColor: "divider",
          bgcolor: "grey.900", minHeight, display: "flex", alignItems: "center",
          justifyContent: "center", overflow: "hidden",
        }}
      >
        {children}
      </Box>
    </Box>
  )
}

export default function SceneCard({
  scene,
  assets,
  projectId,
  onUpdate,
  onGenerate,
  generating,
}) {
  const [saving, setSaving] = useState(false)
  const audioUrl = useMemo(() => mediaSrc(scene.audio_preview_url), [scene.audio_preview_url])
  const startFrameUrl = useMemo(() => {
    if (scene.start_frame_preview_url) return mediaSrc(scene.start_frame_preview_url)
    if (scene.source?.preview_thumb_url) return mediaSrc(scene.source.preview_thumb_url)
    if (scene.type !== "ltx" && scene.visual_preview_url && scene.render_status !== "done") {
      return mediaSrc(scene.visual_preview_url)
    }
    return ""
  }, [scene.start_frame_preview_url, scene.source?.preview_thumb_url, scene.visual_preview_url, scene.type, scene.render_status])

  const renderedVideoUrl = useMemo(() => {
    if (scene.render_status === "done" && scene.rendered_video_url) {
      return mediaSrc(scene.rendered_video_url)
    }
    return ""
  }, [scene.render_status, scene.rendered_video_url])

  const needsGenerate = scene.render_status !== "done"
  const isRendered = scene.render_status === "done"

  const startFrameLabel = scene.type === "ltx"
    ? "Start frame (stock photo)"
    : scene.type === "stock"
      ? "Source clip"
      : "Source asset"

  const handleTypeChange = async (type) => {
    setSaving(true)
    try {
      const { data } = await http.put(`/api/longform/projects/${projectId}/scenes/${scene.id}`, { type })
      onUpdate(data.storyboard)
    } finally {
      setSaving(false)
    }
  }

  const handleAssetChange = async (assetId) => {
    setSaving(true)
    try {
      const { data } = await http.put(`/api/longform/projects/${projectId}/scenes/${scene.id}`, {
        source: { ...(scene.source || {}), asset_id: assetId },
      })
      onUpdate(data.storyboard)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Paper variant="outlined" sx={{ p: 2 }}>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }} flexWrap="wrap">
        <Typography variant="subtitle2" sx={{ fontWeight: 700 }}>
          {scene.id} · {fmtTime(scene.start_s)} – {fmtTime(scene.end_s)}
        </Typography>
        <Chip label={scene.type} size="small" color="primary" variant="outlined" />
        {scene.needs_gpu && <Chip label="LTX + stock photo" size="small" color="warning" />}
        <Chip
          label={scene.visual_status || "pending"}
          size="small"
          color={isRendered ? "success" : "default"}
        />
      </Stack>

      {scene.transcript && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
            Transcript (auto-detected)
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ fontStyle: "italic" }}>
            "{scene.transcript.slice(0, 160)}{scene.transcript.length > 160 ? "…" : ""}"
          </Typography>
        </Box>
      )}
      {scene.visual_keywords_en && (
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
            B-roll keywords (English)
          </Typography>
          <Typography variant="body2" color="text.primary">
            {scene.visual_keywords_en}
          </Typography>
        </Box>
      )}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} sx={{ mb: 2 }}>
        <PreviewBox label="Audio (fixed)">
          <Box component="audio" controls preload="metadata" src={audioUrl} sx={{ width: "100%", px: 1 }} />
        </PreviewBox>
      </Stack>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
        <PreviewBox label={startFrameLabel}>
          {generating && !startFrameUrl ? (
            <CircularProgress size={28} />
          ) : startFrameUrl ? (
            <Box component="img" src={startFrameUrl} alt="" sx={{ width: "100%", maxHeight: 200, objectFit: "contain" }} />
          ) : (
            <Typography variant="caption" color="text.secondary">No source preview</Typography>
          )}
        </PreviewBox>

        <PreviewBox label={isRendered ? "Generated video" : "Generated video (pending)"}>
          {generating || scene.visual_status === "generating" ? (
            <CircularProgress size={28} />
          ) : renderedVideoUrl ? (
            <Box component="video" src={renderedVideoUrl} controls muted sx={{ width: "100%", maxHeight: 200 }} />
          ) : (
            <Typography variant="caption" color="text.secondary">
              {needsGenerate ? "Generate to preview" : "—"}
            </Typography>
          )}
        </PreviewBox>
      </Stack>

      <Stack direction={{ xs: "column", sm: "row" }} spacing={1} sx={{ mt: 0.5 }} alignItems="flex-start">
        <FormControl size="small" sx={{ minWidth: 140 }}>
          <InputLabel>Type</InputLabel>
          <Select
            value={scene.type}
            label="Type"
            disabled={saving}
            onChange={(e) => handleTypeChange(e.target.value)}
          >
            {SCENE_TYPES.map((t) => (
              <MenuItem key={t} value={t}>{t}</MenuItem>
            ))}
          </Select>
        </FormControl>

        {assets?.length > 0 && scene.type !== "stock" && scene.type !== "ltx" && (
          <FormControl size="small" sx={{ minWidth: 160, flex: 1 }}>
            <InputLabel>Asset</InputLabel>
            <Select
              value={scene.source?.asset_id || ""}
              label="Asset"
              disabled={saving}
              onChange={(e) => handleAssetChange(e.target.value)}
            >
              {assets.map((a) => (
                <MenuItem key={a.id} value={a.id}>
                  {a.kind}: {(a.catalog?.description || a.media_url?.split("/").pop()).slice(0, 40)}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        )}

        {scene.type === "stock" && (
          <TextField
            size="small"
            label="Stock query"
            defaultValue={scene.source?.query || ""}
            sx={{ flex: 1 }}
            onBlur={async (e) => {
              if (e.target.value === scene.source?.query) return
              setSaving(true)
              try {
                const { data } = await http.put(`/api/longform/projects/${projectId}/scenes/${scene.id}`, {
                  source: { ...scene.source, query: e.target.value },
                })
                onUpdate(data.storyboard)
              } finally {
                setSaving(false)
              }
            }}
          />
        )}

        {scene.type === "ltx" && (
          <TextField
            size="small"
            label="Stock photo query (LTX start frame)"
            defaultValue={scene.source?.stock_image_query || ""}
            sx={{ flex: 1 }}
            onBlur={async (e) => {
              if (e.target.value === scene.source?.stock_image_query) return
              setSaving(true)
              try {
                const { data } = await http.put(`/api/longform/projects/${projectId}/scenes/${scene.id}`, {
                  source: { ...scene.source, stock_image_query: e.target.value },
                })
                onUpdate(data.storyboard)
              } finally {
                setSaving(false)
              }
            }}
          />
        )}

        {(needsGenerate || scene.render_status === "failed") && (
          <Button
            size="small"
            variant="outlined"
            startIcon={generating ? <CircularProgress size={14} /> : <RefreshIcon />}
            disabled={generating}
            onClick={() => onGenerate(scene.id)}
          >
            {scene.render_status === "failed" ? "Retry" : "Generate"}
          </Button>
        )}
      </Stack>

      {scene.error && (
        <Typography variant="caption" color="error" sx={{ mt: 1, display: "block" }}>
          {scene.error}
        </Typography>
      )}
    </Paper>
  )
}
