import { useState, useEffect, useCallback, useRef } from "react"
import {
  Box, Typography, Paper, Stack, Chip, IconButton, Button, Divider,
  TextField, Tooltip, CircularProgress, Slider, Menu, MenuItem,
  ListItemText, ListItemIcon, Skeleton, Badge, alpha, FormControlLabel, Checkbox,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from "@mui/material"
import ContentCutIcon from "@mui/icons-material/ContentCut"
import WhatshotIcon from "@mui/icons-material/Whatshot"
import AccessTimeIcon from "@mui/icons-material/AccessTime"
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline"
import UploadIcon from "@mui/icons-material/Upload"
import EditIcon from "@mui/icons-material/Edit"
import SaveIcon from "@mui/icons-material/Save"
import DeleteIcon from "@mui/icons-material/Delete"
import PhotoCameraIcon from "@mui/icons-material/PhotoCamera"
import DownloadIcon from "@mui/icons-material/Download"
import AspectRatioIcon from "@mui/icons-material/AspectRatio"
import WarningAmberIcon from "@mui/icons-material/WarningAmber"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import SearchIcon from "@mui/icons-material/Search"
import RefreshIcon from "@mui/icons-material/Refresh"
import SortIcon from "@mui/icons-material/Sort"
import CloseIcon from "@mui/icons-material/Close"
import CheckCircleIcon from "@mui/icons-material/CheckCircle"
import VideocamIcon from "@mui/icons-material/Videocam"
import FolderOpenIcon from "@mui/icons-material/FolderOpen"
import http from "../api/http"
import useAppStore from "../store/appStore"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"

/* ── Helpers ───────────────────────────────────────────────── */

function formatTime(seconds) {
  if (seconds == null) return "--:--"
  const m = Math.floor(seconds / 60)
  const s = Math.floor(seconds % 60)
  return `${m}:${String(s).padStart(2, "0")}`
}

function viralityColor(score) {
  if (score >= 8) return "success"
  if (score >= 6) return "warning"
  return "default"
}

function viralityLabel(score) {
  if (score >= 9) return "Viral"
  if (score >= 8) return "Strong"
  if (score >= 6) return "Good"
  if (score >= 4) return "Average"
  return "Low"
}

/* ── Source Video Sidebar Item ──────────────────────────────── */

function SourceVideoCard({ video, clipCount, isSelected, onClick }) {
  return (
    <Paper
      elevation={0}
      onClick={onClick}
      sx={{
        p: 1.5, cursor: "pointer",
        border: 2,
        borderColor: isSelected ? "primary.main" : "transparent",
        borderRadius: 2.5,
        bgcolor: isSelected ? "action.selected" : "transparent",
        transition: "all 0.2s ease",
        "&:hover": {
          bgcolor: isSelected ? "action.selected" : "action.hover",
          borderColor: isSelected ? "primary.main" : "divider",
        },
      }}
    >
      {/* Thumbnail */}
      <Box sx={{
        width: "100%", aspectRatio: "16/9", borderRadius: 2, overflow: "hidden",
        bgcolor: "action.hover", mb: 1, position: "relative",
      }}>
        {(video.thumbnail_path || video.thumbnail_url) ? (
          <Box component="img"
            src={video.thumbnail_path ? `/api/downloaded/${video.id}/thumbnail` : video.thumbnail_url}
            alt=""
            sx={{ width: "100%", height: "100%", objectFit: "cover" }}
            onError={e => { e.target.style.display = "none" }} />
        ) : (
          <Box sx={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <VideocamIcon sx={{ color: "text.disabled", fontSize: 28 }} />
          </Box>
        )}
        {/* Duration badge */}
        {video.duration_seconds > 0 && (
          <Chip
            label={formatTime(video.duration_seconds)}
            size="small"
            sx={{
              position: "absolute", bottom: 4, right: 4,
              height: 20, fontSize: "0.65rem", fontWeight: 700,
              bgcolor: "rgba(0,0,0,0.75)", color: "#fff",
              "& .MuiChip-label": { px: 0.75 },
            }}
          />
        )}
      </Box>

      <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem", lineHeight: 1.3 }} noWrap>
        {video.title || "Untitled"}
      </Typography>
      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
        <ContentCutIcon sx={{ fontSize: 13, color: clipCount > 0 ? "primary.main" : "text.disabled" }} />
        <Typography variant="caption" sx={{ color: clipCount > 0 ? "primary.main" : "text.secondary", fontWeight: clipCount > 0 ? 700 : 400 }}>
          {clipCount} clip{clipCount !== 1 ? "s" : ""}
        </Typography>
      </Stack>
    </Paper>
  )
}

/* ── Clip Filmstrip Card ───────────────────────────────────── */

function ClipCard({ clip, isSelected, onClick }) {
  const score = clip.clip_virality_score
  return (
    <Paper
      elevation={0}
      onClick={onClick}
      sx={{
        width: 140, minWidth: 140, flexShrink: 0,
        cursor: "pointer",
        border: 2,
        borderColor: isSelected ? "primary.main" : "transparent",
        borderRadius: 2.5,
        overflow: "hidden",
        transition: "all 0.2s ease",
        transform: isSelected ? "translateY(-2px)" : "none",
        boxShadow: isSelected ? (t) => `0 4px 16px ${alpha(t.palette.primary.main, 0.25)}` : "none",
        "&:hover": {
          borderColor: isSelected ? "primary.main" : "divider",
          transform: "translateY(-2px)",
          boxShadow: (t) => `0 4px 12px ${alpha(t.palette.common.black, 0.1)}`,
        },
      }}
    >
      {/* Thumbnail */}
      <Box sx={{ width: "100%", aspectRatio: "9/16", position: "relative", bgcolor: "#000" }}>
        {clip.thumbnail_path ? (
          <Box component="img" src={`/api/videos/${clip.id}/thumbnail`} alt=""
            sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <Box sx={{ width: "100%", height: "100%", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <ContentCutIcon sx={{ color: "rgba(255,255,255,0.3)", fontSize: 28 }} />
          </Box>
        )}
        {/* Virality badge */}
        {score != null && (
          <Chip
            icon={<WhatshotIcon sx={{ fontSize: "14px !important" }} />}
            label={score.toFixed(1)}
            size="small"
            color={viralityColor(score)}
            sx={{
              position: "absolute", top: 4, left: 4,
              height: 22, fontWeight: 700, fontSize: "0.7rem",
              "& .MuiChip-icon": { ml: 0.3 },
            }}
          />
        )}
        {/* Duration badge */}
        <Chip
          label={formatTime(clip.duration_seconds)}
          size="small"
          sx={{
            position: "absolute", bottom: 4, right: 4,
            height: 18, fontSize: "0.6rem", fontWeight: 700,
            bgcolor: "rgba(0,0,0,0.75)", color: "#fff",
            "& .MuiChip-label": { px: 0.5 },
          }}
        />
        {/* Caption warning */}
        {clip.caption_status === "failed" && (
          <Tooltip title="Captions failed to apply">
            <WarningAmberIcon sx={{ position: "absolute", top: 4, right: 4, fontSize: 18, color: "warning.main" }} />
          </Tooltip>
        )}
        {/* Play overlay */}
        <Box sx={{
          position: "absolute", inset: 0,
          display: "flex", alignItems: "center", justifyContent: "center",
          opacity: 0, transition: "opacity 0.2s",
          bgcolor: "rgba(0,0,0,0.3)",
          "&:hover": { opacity: 1 },
        }}>
          <PlayCircleOutlineIcon sx={{ fontSize: 36, color: "#fff" }} />
        </Box>
      </Box>

      {/* Title */}
      <Box sx={{ p: 1 }}>
        <Typography variant="caption" sx={{ fontWeight: 600, fontSize: "0.7rem", lineHeight: 1.2, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
          {clip.title || "Untitled Clip"}
        </Typography>
      </Box>
    </Paper>
  )
}

/* ── Extract Clips Dialog ──────────────────────────────────── */

const WHISPER_QUALITIES = [
  { value: "fast", label: "Fast (base)", desc: "~30s per 5min video" },
  { value: "balanced", label: "Balanced (small)", desc: "~90s per 5min video" },
  { value: "accurate", label: "Accurate (medium)", desc: "~3min per 5min video" },
  { value: "best", label: "Best (large-v3)", desc: "~8min per 5min video" },
]

function ExtractDialog({ open, onClose, video, onExtract }) {
  const hasSegments = !!video?.has_transcript_segments
  const [opts, setOpts] = useState({ caption_style: "viral", min_duration: null, max_duration: null, whisper_quality: "balanced", retranscribe: false })

  // Reset retranscribe when video changes
  useEffect(() => { setOpts(p => ({ ...p, retranscribe: false })) }, [video?.id])

  if (!video) return null

  const transcribeEnabled = !hasSegments || opts.retranscribe
  const durationError = opts.min_duration && opts.max_duration && opts.max_duration - opts.min_duration < 1
  const canSubmit = !durationError

  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <ContentCutIcon color="primary" /> Extract Clips
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ color: "text.secondary", mb: 2 }}>
          From: <strong>{video.title || "Untitled"}</strong> ({formatTime(video.duration_seconds)})
        </Typography>
        <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mb: 2.5 }}>
          AI will analyze the transcript and automatically find the best viral moments. The number of clips depends on how much quality content the video has.
        </Typography>
        <Stack spacing={2.5}>
          {/* Transcription */}
          <Box>
            <FormControlLabel
              control={
                <Checkbox
                  checked={transcribeEnabled}
                  onChange={e => setOpts(p => ({ ...p, retranscribe: e.target.checked }))}
                  disabled={!hasSegments}
                  size="small"
                />
              }
              label={
                <Typography variant="caption" sx={{ fontWeight: 600 }}>
                  Transcription {hasSegments
                    ? <Chip label="cached" size="small" color="success" variant="outlined" sx={{ ml: 0.5, height: 18, fontSize: "0.65rem" }} />
                    : <Chip label="required" size="small" color="warning" variant="outlined" sx={{ ml: 0.5, height: 18, fontSize: "0.65rem" }} />
                  }
                </Typography>
              }
              sx={{ mb: 0.5 }}
            />
            {!hasSegments && (
              <Typography variant="caption" sx={{ color: "text.secondary", display: "block", ml: 4, mb: 1 }}>
                No word-level transcript found — Whisper will transcribe the audio first
              </Typography>
            )}
            {hasSegments && !opts.retranscribe && (
              <Typography variant="caption" sx={{ color: "success.main", display: "block", ml: 4, mb: 1 }}>
                Using cached transcript — Whisper will be skipped
              </Typography>
            )}
            {hasSegments && opts.retranscribe && (
              <Typography variant="caption" sx={{ color: "warning.main", display: "block", ml: 4, mb: 1 }}>
                Will re-transcribe with selected model (replaces cached transcript)
              </Typography>
            )}
            <TextField select size="small" fullWidth
              value={opts.whisper_quality}
              onChange={e => setOpts(p => ({ ...p, whisper_quality: e.target.value }))}
              disabled={!transcribeEnabled}
              sx={{ ml: 0 }}
            >
              {WHISPER_QUALITIES.map(q => (
                <MenuItem key={q.value} value={q.value}>
                  <Stack direction="row" justifyContent="space-between" sx={{ width: "100%" }}>
                    <Typography variant="body2">{q.label}</Typography>
                    <Typography variant="caption" sx={{ color: "text.secondary", ml: 2 }}>{q.desc}</Typography>
                  </Stack>
                </MenuItem>
              ))}
            </TextField>
          </Box>

          {/* Caption style */}
          <Box>
            <Typography variant="caption" sx={{ fontWeight: 600, mb: 0.5, display: "block" }}>Caption style</Typography>
            <Stack direction="row" spacing={1}>
              {["viral", "classic", "bold", "none"].map(s => (
                <Chip key={s} label={s} size="small"
                  variant={opts.caption_style === s ? "filled" : "outlined"}
                  color={opts.caption_style === s ? "primary" : "default"}
                  onClick={() => setOpts(p => ({ ...p, caption_style: s }))}
                  sx={{ textTransform: "capitalize", cursor: "pointer" }} />
              ))}
            </Stack>
          </Box>

          {/* Duration range */}
          <Box>
            <Typography variant="caption" sx={{ fontWeight: 600, mb: 0.5, display: "block" }}>
              Clip duration range (leave empty for auto 15–60s)
            </Typography>
            <Stack direction="row" spacing={2} alignItems="center">
              <TextField label="Min (s)" type="number" size="small" sx={{ width: 90 }}
                value={opts.min_duration || ""}
                error={!!durationError}
                slotProps={{ htmlInput: { min: 10, max: 120 } }}
                onChange={e => setOpts(p => ({ ...p, min_duration: parseInt(e.target.value) || null }))} />
              <Typography variant="body2" sx={{ color: "text.secondary" }}>to</Typography>
              <TextField label="Max (s)" type="number" size="small" sx={{ width: 90 }}
                value={opts.max_duration || ""}
                error={!!durationError}
                slotProps={{ htmlInput: { min: 15, max: 180 } }}
                onChange={e => setOpts(p => ({ ...p, max_duration: parseInt(e.target.value) || null }))} />
            </Stack>
            {durationError && (
              <Typography variant="caption" sx={{ color: "error.main", mt: 0.5, display: "block" }}>
                Max must be at least 1 second greater than Min
              </Typography>
            )}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" startIcon={<ContentCutIcon />}
          disabled={!canSubmit}
          onClick={() => { onExtract(video.id, { ...opts, force_retranscribe: transcribeEnabled }); onClose() }}>
          Extract Clips
        </Button>
      </DialogActions>
    </Dialog>
  )
}


/* ══════════════════════════════════════════════════════════════
   MAIN COMPONENT: Clip Studio
   ══════════════════════════════════════════════════════════════ */

export default function ClipStudio() {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const activeJobs = useAppStore((s) => s.activeJobs)

  // Track clip extraction jobs (restored from API on page load via useWebSocket)
  const isClipJob = (j) =>
    (j.message && j.message.toLowerCase().includes("clip"))
    || (j.inputData && j.inputData.type === "clip_extraction")
  const clipJobs = Object.values(activeJobs).filter(isClipJob)
  const clipJobFilter = (j) => j.status === "running" && isClipJob(j)
  const justCompletedRef = useRef(new Set())

  // Data
  const [sources, setSources] = useState([])
  const [clips, setClips] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedSourceId, setSelectedSourceId] = useState(null) // "all" or video id
  const [selectedClip, setSelectedClip] = useState(null)
  const [sourceFilter, setSourceFilter] = useState("")
  const [searchQuery, setSearchQuery] = useState("")
  const [sortBy, setSortBy] = useState("virality") // virality | newest | duration
  const [sortAnchor, setSortAnchor] = useState(null)

  // Extract dialog
  const [extractDialogOpen, setExtractDialogOpen] = useState(false)
  const [extractTarget, setExtractTarget] = useState(null)
  const [extracting, setExtracting] = useState(false)

  // Edit mode
  const [editing, setEditing] = useState(false)
  const [editDraft, setEditDraft] = useState({})
  const [saving, setSaving] = useState(false)

  // Regen thumbnail
  const [regenThumb, setRegenThumb] = useState(false)

  // Video player ref
  const videoRef = useRef(null)

  // ── Load data ────────────────────────────────────────────────
  const fetchData = useCallback(async () => {
    try {
      const [srcRes, clipRes] = await Promise.all([
        http.get("/api/downloaded", { params: { limit: 200 } }),
        http.get("/api/videos", { params: { limit: 100 } }),
      ])
      // Show all downloaded videos (sorted longest first — best for clipping)
      const downloadedVideos = (srcRes.data?.videos || srcRes.data || [])
        .sort((a, b) => (b.duration_seconds || 0) - (a.duration_seconds || 0))
      setSources(downloadedVideos)

      // Only show clip_extraction videos
      const clipVideos = (clipRes.data.videos || []).filter(v => v.source_type === "clip_extraction")
      setClips(clipVideos)

      // Don't auto-select — let user choose from filmstrip or sidebar
    } catch (e) {
      console.error("Failed to load clip studio data:", e)
      showSnackbar("Failed to load clip data", "error")
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchData() }, [fetchData])

  // Auto-refresh when a clip extraction job completes
  useEffect(() => {
    for (const job of clipJobs) {
      if ((job.status === "success" || job.status === "failed") && !justCompletedRef.current.has(job.jobId)) {
        justCompletedRef.current.add(job.jobId)
        // Prevent unbounded growth — keep only the last 50 entries
        if (justCompletedRef.current.size > 50) {
          const entries = [...justCompletedRef.current]
          justCompletedRef.current = new Set(entries.slice(-25))
        }
        if (job.status === "success") {
          // Delay slightly so backend has time to persist clips
          setTimeout(() => fetchData(), 1500)
        }
      }
    }
  }, [clipJobs, fetchData])

  // ── Derived data ─────────────────────────────────────────────
  const clipCountBySource = {}
  clips.forEach(c => {
    const sid = c.source_downloaded_video_id
    if (sid) clipCountBySource[sid] = (clipCountBySource[sid] || 0) + 1
  })

  // Only show clips when a source is selected (or "all" explicitly chosen)
  const showAllClips = selectedSourceId === "all"
  const filteredClips = clips
    .filter(c => {
      if (!selectedSourceId && !showAllClips) return false  // nothing selected → show nothing
      if (selectedSourceId && selectedSourceId !== "all") {
        if (c.source_downloaded_video_id !== selectedSourceId) return false
      }
      if (searchQuery) {
        const q = searchQuery.toLowerCase()
        return (c.title || "").toLowerCase().includes(q) ||
          (c.youtube_title || "").toLowerCase().includes(q)
      }
      return true
    })
    .sort((a, b) => {
      if (sortBy === "virality") return (b.clip_virality_score || 0) - (a.clip_virality_score || 0)
      if (sortBy === "newest") return new Date(b.created_at || 0) - new Date(a.created_at || 0)
      if (sortBy === "duration") return (b.duration_seconds || 0) - (a.duration_seconds || 0)
      return 0
    })

  // ── Handlers ─────────────────────────────────────────────────

  const handleExtract = async (videoId, opts) => {
    setExtracting(true)
    try {
      const payload = { caption_style: opts.caption_style }
      if (opts.force_retranscribe) {
        payload.whisper_quality = opts.whisper_quality
        payload.force_retranscribe = true
      }
      if (opts.min_duration) payload.min_duration = opts.min_duration
      if (opts.max_duration) payload.max_duration = opts.max_duration
      await http.post(`/api/downloaded/${videoId}/extract-clips`, payload)
      showSnackbar("Extracting viral clips — AI will find the best moments", "success")
    } catch (e) {
      showSnackbar(`Extract failed: ${e.response?.data?.detail || e.message}`, "error")
    } finally {
      setExtracting(false)
    }
  }

  const handleUpload = async (platform) => {
    if (!selectedClip) return
    try {
      await http.post(`/api/videos/${selectedClip.id}/upload`, { platforms: [platform] })
      showSnackbar(`Uploading to ${platform}...`, "success")
    } catch (e) {
      showSnackbar(`Upload failed: ${e.response?.data?.detail || e.message}`, "error")
    }
  }

  const handleDelete = async () => {
    if (!selectedClip) return
    try {
      await http.delete(`/api/videos/${selectedClip.id}`)
      showSnackbar("Clip deleted", "success")
      setClips(prev => prev.filter(c => c.id !== selectedClip.id))
      setSelectedClip(null)
    } catch (e) {
      showSnackbar(`Delete failed: ${e.response?.data?.detail || e.message}`, "error")
    }
  }

  const handleRegenThumbnail = async () => {
    if (!selectedClip) return
    setRegenThumb(true)
    try {
      const res = await http.post(`/api/videos/${selectedClip.id}/regenerate-thumbnail`)
      showSnackbar("Thumbnail regenerated!", "success")
      setSelectedClip(prev => ({ ...prev, thumbnail_path: res.data.thumbnail_path }))
      setClips(prev => prev.map(c => c.id === selectedClip.id ? { ...c, thumbnail_path: res.data.thumbnail_path } : c))
    } catch (e) {
      showSnackbar(`Thumbnail regen failed: ${e.response?.data?.detail || e.message}`, "error")
    } finally {
      setRegenThumb(false)
    }
  }

  const startEditing = () => {
    if (!selectedClip) return
    setEditDraft({
      title: selectedClip.title || "",
      youtube_title: selectedClip.youtube_title || "",
      youtube_description: selectedClip.youtube_description || "",
      youtube_tags: (selectedClip.youtube_tags || []).join(", "),
      tiktok_title: selectedClip.tiktok_title || "",
    })
    setEditing(true)
  }

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await http.patch(`/api/videos/${selectedClip.id}`, editDraft)
      showSnackbar("Clip metadata updated", "success")
      const updated = { ...selectedClip, ...res.data, youtube_tags: res.data.youtube_tags }
      setSelectedClip(updated)
      setClips(prev => prev.map(c => c.id === updated.id ? { ...c, ...updated } : c))
      setEditing(false)
    } catch (e) {
      showSnackbar(`Save failed: ${e.response?.data?.detail || e.message}`, "error")
    } finally {
      setSaving(false)
    }
  }

  // ── Render ───────────────────────────────────────────────────

  if (loading) {
    return (
      <Box sx={{ p: 3, display: "flex", flexDirection: "column", gap: 2 }}>
        <Skeleton variant="rounded" height={40} width={300} />
        <Stack direction="row" spacing={2}>
          <Skeleton variant="rounded" width={200} height={400} />
          <Skeleton variant="rounded" sx={{ flex: 1 }} height={400} />
        </Stack>
      </Box>
    )
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>

      {/* ── Header ──────────────────────────────────────────── */}
      <Box sx={{
        px: 3, py: 2, flexShrink: 0,
        borderBottom: 1, borderColor: "divider",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: (t) => t.palette.mode === "dark"
          ? "linear-gradient(135deg, rgba(201,100,66,0.08) 0%, rgba(30,28,26,1) 100%)"
          : "linear-gradient(135deg, rgba(201,100,66,0.06) 0%, rgba(255,255,255,1) 100%)",
      }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <ContentCutIcon sx={{ color: "primary.main", fontSize: 26 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: -0.3 }}>
              Clip Studio
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              {clips.length} clip{clips.length !== 1 ? "s" : ""} from {sources.length} video{sources.length !== 1 ? "s" : ""}
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" spacing={1}>
          {/* Search */}
          <TextField
            placeholder="Search clips..."
            size="small"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            slotProps={{ input: { startAdornment: <SearchIcon sx={{ mr: 0.5, fontSize: 18, color: "text.secondary" }} /> } }}
            sx={{ width: 200 }}
          />

          {/* Sort */}
          <Button size="small" variant="outlined" startIcon={<SortIcon />}
            onClick={e => setSortAnchor(e.currentTarget)} sx={{ textTransform: "none" }}>
            {sortBy === "virality" ? "Top Viral" : sortBy === "newest" ? "Newest" : "Longest"}
          </Button>
          <Menu anchorEl={sortAnchor} open={Boolean(sortAnchor)} onClose={() => setSortAnchor(null)}>
            {[
              { key: "virality", label: "Top Viral", icon: <WhatshotIcon fontSize="small" /> },
              { key: "newest", label: "Newest First", icon: <AccessTimeIcon fontSize="small" /> },
              { key: "duration", label: "Longest First", icon: <AspectRatioIcon fontSize="small" /> },
            ].map(s => (
              <MenuItem key={s.key} selected={sortBy === s.key}
                onClick={() => { setSortBy(s.key); setSortAnchor(null) }}>
                <ListItemIcon>{s.icon}</ListItemIcon>
                <ListItemText>{s.label}</ListItemText>
              </MenuItem>
            ))}
          </Menu>

          {/* Open Folder */}
          <Tooltip title="Open clips folder">
            <Button size="small" variant="outlined" sx={{ minWidth: 0, px: 1 }}
              onClick={() => http.post("/api/settings/open-folder", { folder: "generated" }).catch(() => showSnackbar("Could not open folder", "error"))}>
              <FolderOpenIcon fontSize="small" />
            </Button>
          </Tooltip>

          {/* Refresh */}
          <Tooltip title="Refresh sources & clips">
            <Button size="small" variant="outlined" onClick={() => { setLoading(true); fetchData() }}
              startIcon={<RefreshIcon fontSize="small" />}
              sx={{ textTransform: "none" }}>
              Refresh
            </Button>
          </Tooltip>
        </Stack>
      </Box>

      {/* ── Active Jobs Progress ──────────────────────────────── */}
      <ActiveJobsBanner filter={clipJobFilter} fallbackLabel="Extracting clips…" />

      {/* ── Main Layout ─────────────────────────────────────── */}
      <Box sx={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* ── Left: Source Videos ────────────────────────────── */}
        <Box sx={{
          width: 200, flexShrink: 0, overflow: "auto",
          borderRight: 1, borderColor: "divider",
          p: 1.5, display: "flex", flexDirection: "column", gap: 0.5,
        }}>
          <Typography variant="overline" sx={{ color: "text.secondary", px: 0.5, fontSize: "0.65rem" }}>
            Source Videos
          </Typography>

          <TextField
            size="small"
            placeholder="Filter..."
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value)}
            slotProps={{ input: { startAdornment: <SearchIcon sx={{ fontSize: 14, color: "text.disabled", mr: 0.5 }} /> } }}
            sx={{ "& .MuiInputBase-root": { fontSize: "0.75rem", height: 28, px: 0.5 } }}
          />

          {/* "All" filter */}
          <Paper
            elevation={0}
            onClick={() => {
              setSelectedSourceId("all")
              // Auto-select first clip overall
              if (clips.length > 0) setSelectedClip(clips[0])
            }}
            sx={{
              p: 1, cursor: "pointer", borderRadius: 2,
              border: 2, borderColor: selectedSourceId === "all" ? "primary.main" : "transparent",
              bgcolor: selectedSourceId === "all" ? "action.selected" : "transparent",
              "&:hover": { bgcolor: "action.hover" },
              transition: "all 0.15s",
            }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <ContentCutIcon sx={{ fontSize: 16, color: "primary.main" }} />
              <Typography variant="body2" sx={{ fontWeight: 600, fontSize: "0.8rem" }}>
                All Clips ({clips.length})
              </Typography>
            </Stack>
          </Paper>

          <Divider sx={{ my: 0.5 }} />

          {sources.filter(v => !sourceFilter || (v.title || "").toLowerCase().includes(sourceFilter.toLowerCase())).map(v => (
            <SourceVideoCard
              key={v.id}
              video={v}
              clipCount={clipCountBySource[v.id] || 0}
              isSelected={selectedSourceId === v.id}
              onClick={() => {
                const newId = selectedSourceId === v.id ? null : v.id
                setSelectedSourceId(newId)
                // Auto-select first clip from this source (or first overall if deselecting)
                if (newId) {
                  const sourceClips = clips.filter(c => c.source_downloaded_video_id === newId)
                  if (sourceClips.length > 0) setSelectedClip(sourceClips[0])
                  else setSelectedClip(null)
                } else {
                  setSelectedClip(null)
                }
              }}
            />
          ))}

          {sources.length === 0 && (
            <Box sx={{ p: 2, textAlign: "center" }}>
              <Typography variant="caption" sx={{ color: "text.disabled" }}>
                No source videos yet. Download some videos from the Library first.
              </Typography>
            </Box>
          )}
        </Box>

        {/* ── Center: Preview + Details ──────────────────────── */}
        <Box sx={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>

          {selectedClip ? (
            <Box sx={{ flex: 1, overflow: "auto", p: 3 }}>
              <Box sx={{ display: "flex", gap: 3, maxWidth: 1200, mx: "auto" }}>

                {/* Video Player */}
                <Box sx={{ width: 320, flexShrink: 0 }}>
                  <Paper
                    elevation={0}
                    sx={{
                      borderRadius: 3, overflow: "hidden",
                      bgcolor: "#000", position: "relative",
                      border: 1, borderColor: "divider",
                    }}
                  >
                    <Box
                      ref={videoRef}
                      component="video"
                      controls
                      autoPlay={false}
                      key={selectedClip.id}
                      sx={{ width: "100%", display: "block", maxHeight: 560 }}
                      src={`/api/videos/${selectedClip.id}/stream`}
                    />
                  </Paper>

                  {/* Source context */}
                  {selectedClip.clip_start_seconds != null && (
                    <Paper variant="outlined" sx={{ mt: 1.5, p: 1.5, borderRadius: 2 }}>
                      <Stack direction="row" spacing={1} alignItems="center">
                        <AccessTimeIcon sx={{ fontSize: 16, color: "text.secondary" }} />
                        <Typography variant="caption" sx={{ color: "text.secondary" }}>
                          {formatTime(selectedClip.clip_start_seconds)} — {formatTime(selectedClip.clip_end_seconds)} in source
                        </Typography>
                      </Stack>
                    </Paper>
                  )}

                  {/* Quick stats */}
                  <Stack direction="row" spacing={1} sx={{ mt: 1.5 }} flexWrap="wrap" useFlexGap>
                    {selectedClip.clip_virality_score != null && (
                      <Chip
                        icon={<WhatshotIcon />}
                        label={`${selectedClip.clip_virality_score.toFixed(1)} — ${viralityLabel(selectedClip.clip_virality_score)}`}
                        size="small" variant="filled"
                        color={viralityColor(selectedClip.clip_virality_score)}
                      />
                    )}
                    <Chip label={`${formatTime(selectedClip.duration_seconds)}`} icon={<AccessTimeIcon />} size="small" variant="outlined" />
                    <Chip label="9:16" size="small" variant="outlined" />
                    {selectedClip.caption_status === "applied" && (
                      <Chip icon={<CheckCircleIcon />} label="Captions" size="small" color="success" variant="outlined" />
                    )}
                    {selectedClip.caption_status === "failed" && (
                      <Chip icon={<WarningAmberIcon />} label="Captions failed" size="small" color="warning" variant="filled" />
                    )}
                    {selectedClip.metadata_status === "fallback" && (
                      <Chip icon={<WarningAmberIcon />} label="AI meta failed" size="small" color="warning" variant="outlined" />
                    )}
                  </Stack>
                </Box>

                {/* Metadata + Actions */}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  {/* Action bar */}
                  <Stack direction="row" spacing={1} sx={{ mb: 2 }} flexWrap="wrap" useFlexGap>
                    {!editing ? (
                      <>
                        <Button size="small" variant="outlined" startIcon={<EditIcon />} onClick={startEditing}>
                          Edit
                        </Button>
                        <Button size="small" variant="outlined"
                          startIcon={regenThumb ? <CircularProgress size={14} /> : <PhotoCameraIcon />}
                          disabled={regenThumb} onClick={handleRegenThumbnail}>
                          {regenThumb ? "Generating..." : "Regen Thumbnail"}
                        </Button>
                        <Button size="small" variant="contained" color="error" startIcon={<UploadIcon />}
                          onClick={() => handleUpload("youtube")}>
                          YouTube
                        </Button>
                        <Button size="small" variant="contained" color="info" startIcon={<UploadIcon />}
                          onClick={() => handleUpload("tiktok")}>
                          TikTok
                        </Button>
                        <Button size="small" variant="outlined" color="inherit" startIcon={<DeleteIcon />}
                          onClick={handleDelete}>
                          Delete
                        </Button>
                      </>
                    ) : (
                      <>
                        <Button size="small" variant="contained" startIcon={saving ? <CircularProgress size={14} /> : <SaveIcon />}
                          disabled={saving} onClick={handleSave}>
                          Save
                        </Button>
                        <Button size="small" variant="outlined" onClick={() => setEditing(false)} disabled={saving}>
                          Cancel
                        </Button>
                      </>
                    )}
                  </Stack>

                  {editing ? (
                    <Stack spacing={2}>
                      <TextField label="Clip Title" size="small" fullWidth
                        value={editDraft.title} onChange={e => setEditDraft(p => ({ ...p, title: e.target.value }))} />
                      <Divider />
                      <Typography variant="overline" sx={{ color: "text.secondary" }}>YouTube Shorts</Typography>
                      <TextField label="Title" size="small" fullWidth
                        value={editDraft.youtube_title} onChange={e => setEditDraft(p => ({ ...p, youtube_title: e.target.value }))} />
                      <TextField label="Description" size="small" fullWidth multiline minRows={2} maxRows={4}
                        value={editDraft.youtube_description} onChange={e => setEditDraft(p => ({ ...p, youtube_description: e.target.value }))} />
                      <TextField label="Tags (comma-separated)" size="small" fullWidth
                        value={editDraft.youtube_tags} onChange={e => setEditDraft(p => ({ ...p, youtube_tags: e.target.value }))} />
                      <Divider />
                      <Typography variant="overline" sx={{ color: "text.secondary" }}>TikTok</Typography>
                      <TextField label="Caption" size="small" fullWidth
                        value={editDraft.tiktok_title} onChange={e => setEditDraft(p => ({ ...p, tiktok_title: e.target.value }))} />
                    </Stack>
                  ) : (
                    <Stack spacing={2}>
                      {/* Title */}
                      <Box>
                        <Typography variant="h6" sx={{ fontWeight: 700, lineHeight: 1.3 }}>
                          {selectedClip.title}
                        </Typography>
                        {selectedClip.clip_virality_reason && (
                          <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5, fontStyle: "italic", fontSize: "0.85rem" }}>
                            {selectedClip.clip_virality_reason}
                          </Typography>
                        )}
                      </Box>

                      {/* YouTube */}
                      {selectedClip.youtube_title && (
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                          <Typography variant="overline" sx={{ color: "error.main", fontWeight: 700, fontSize: "0.65rem" }}>
                            YouTube Shorts
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.5 }}>
                            {selectedClip.youtube_title}
                          </Typography>
                          {selectedClip.youtube_description && (
                            <Typography variant="caption" sx={{ color: "text.secondary", display: "block", mt: 0.5, lineHeight: 1.5 }}>
                              {selectedClip.youtube_description}
                            </Typography>
                          )}
                          {selectedClip.youtube_tags?.length > 0 && (
                            <Stack direction="row" spacing={0.5} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
                              {selectedClip.youtube_tags.map((tag, i) => (
                                <Chip key={i} label={tag} size="small" variant="outlined" sx={{ height: 20, fontSize: "0.6rem" }} />
                              ))}
                            </Stack>
                          )}
                        </Paper>
                      )}

                      {/* TikTok */}
                      {selectedClip.tiktok_title && (
                        <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                          <Typography variant="overline" sx={{ color: "info.main", fontWeight: 700, fontSize: "0.65rem" }}>
                            TikTok
                          </Typography>
                          <Typography variant="body2" sx={{ fontWeight: 600, mt: 0.5 }}>
                            {selectedClip.tiktok_title}
                          </Typography>
                        </Paper>
                      )}

                      {/* Transcript */}
                      {selectedClip.script && (
                        <Box>
                          <Typography variant="overline" sx={{ color: "text.secondary", fontSize: "0.65rem" }}>
                            Transcript
                          </Typography>
                          <Paper variant="outlined" sx={{
                            p: 1.5, maxHeight: 200, overflowY: "auto",
                            fontSize: "0.8rem", color: "text.secondary", lineHeight: 1.6,
                            whiteSpace: "pre-wrap", borderRadius: 2,
                          }}>
                            {selectedClip.script}
                          </Paper>
                        </Box>
                      )}
                    </Stack>
                  )}
                </Box>
              </Box>
            </Box>
          ) : (
            /* Empty state */
            <Box sx={{
              flex: 1, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", gap: 2,
            }}>
              <ContentCutIcon sx={{ fontSize: 64, color: "text.disabled", opacity: 0.3 }} />
              <Typography variant="h6" sx={{ color: "text.disabled" }}>
                {clips.length === 0 ? "No clips yet" : "Select a clip to preview"}
              </Typography>
              <Typography variant="body2" sx={{ color: "text.disabled", textAlign: "center", maxWidth: 360 }}>
                {clips.length === 0
                  ? "Select a source video and click 'Extract Clips' to get started. AI will find the most viral moments."
                  : "Click on a clip in the filmstrip below to preview and manage it."}
              </Typography>
              {clips.length === 0 && sources.length > 0 && (
                <Button variant="contained" startIcon={<ContentCutIcon />}
                  onClick={() => { setExtractTarget(sources[0]); setExtractDialogOpen(true) }}>
                  Extract from {sources[0].title?.slice(0, 30) || "first video"}
                </Button>
              )}
            </Box>
          )}

          {/* ── Bottom: Clip Filmstrip ────────────────────────── */}
          <Box sx={{
            flexShrink: 0,
            borderTop: 1, borderColor: "divider",
            bgcolor: (t) => t.palette.mode === "dark" ? "rgba(0,0,0,0.2)" : "rgba(0,0,0,0.02)",
          }}>
            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ px: 2, pt: 1.5, pb: 0.5 }}>
              <Typography variant="overline" sx={{ color: "text.secondary", fontSize: "0.65rem", flexShrink: 0 }}>
                Clips ({filteredClips.length})
              </Typography>
              <Box sx={{ flex: 1 }} />
              {/* Extract button for selected source */}
              {selectedSourceId && selectedSourceId !== "all" && (
                <Button size="small" variant="contained" color="primary"
                  startIcon={extracting ? <CircularProgress size={14} color="inherit" /> : <ContentCutIcon />}
                  disabled={extracting}
                  onClick={() => {
                    const src = sources.find(s => s.id === selectedSourceId)
                    if (src) { setExtractTarget(src); setExtractDialogOpen(true) }
                  }}
                  sx={{ textTransform: "none", height: 30, fontSize: "0.8rem", fontWeight: 700, px: 2, borderRadius: 2 }}>
                  Extract Clips
                </Button>
              )}
            </Stack>
            <Box sx={{
              display: "flex", flexWrap: "nowrap", gap: 1.5, px: 2, pb: 2, pt: 0.5,
              overflowX: "auto", overflowY: "hidden",
              "&::-webkit-scrollbar": { height: 6 },
              "&::-webkit-scrollbar-thumb": { bgcolor: "divider", borderRadius: 3 },
            }}>
              {filteredClips.length === 0 ? (
                <Box sx={{ py: 3, px: 4, textAlign: "center", width: "100%" }}>
                  <Typography variant="caption" sx={{ color: "text.disabled" }}>
                    {selectedSourceId ? "No clips from this video yet" : "No clips to display"}
                  </Typography>
                </Box>
              ) : (
                filteredClips.map(clip => (
                  <ClipCard
                    key={clip.id}
                    clip={clip}
                    isSelected={selectedClip?.id === clip.id}
                    onClick={() => setSelectedClip(clip)}
                  />
                ))
              )}
            </Box>
          </Box>
        </Box>
      </Box>

      {/* Extract Dialog */}
      <ExtractDialog
        open={extractDialogOpen}
        onClose={() => setExtractDialogOpen(false)}
        video={extractTarget}
        onExtract={handleExtract}
      />
    </Box>
  )
}
