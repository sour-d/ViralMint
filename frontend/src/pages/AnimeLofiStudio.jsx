import { useState, useRef, useEffect, useCallback } from "react"
import {
  Box, Stack, Typography, Paper, Button, CircularProgress,
  Stepper, Step, StepLabel, Chip, Card, CardMedia,
  TextField, Alert, Grid, Tooltip, IconButton,
  Dialog, DialogTitle, DialogContent, DialogActions, List, ListItemButton, ListItemText,
} from "@mui/material"
import http from "../api/http"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import CheckCircleIcon from "@mui/icons-material/CheckCircle"
import MusicNoteIcon from "@mui/icons-material/MusicNote"
import ImageIcon from "@mui/icons-material/Image"
import VideocamIcon from "@mui/icons-material/Videocam"
import ReplayIcon from "@mui/icons-material/Replay"
import SaveIcon from "@mui/icons-material/Save"
import FolderOpenIcon from "@mui/icons-material/FolderOpen"

const STORAGE_KEY = "anime_lofi_studio"
const SNAPSHOTS_KEY = "anime_lofi_snapshots"

const STEPS = [
  { label: "Write Script", icon: <AutoAwesomeIcon /> },
  { label: "Generate Audio", icon: <MusicNoteIcon /> },
  { label: "Create Images", icon: <ImageIcon /> },
  { label: "Generate Videos", icon: <VideocamIcon /> },
  { label: "Render Final", icon: <VideocamIcon /> },
]

function loadSavedState() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    return JSON.parse(raw)
  } catch { return null }
}

function saveState(state) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(state)) } catch { /* ignore quota errors */ }
}

function clearSavedState() {
  try { localStorage.removeItem(STORAGE_KEY) } catch { /* ignore */ }
}

function loadSnapshots() {
  try { return JSON.parse(localStorage.getItem(SNAPSHOTS_KEY) || "[]") } catch { return [] }
}

function saveSnapshot(state, label) {
  const snapshots = loadSnapshots()
  snapshots.push({ label, savedAt: Date.now(), state })
  // Keep most recent 20
  try { localStorage.setItem(SNAPSHOTS_KEY, JSON.stringify(snapshots.slice(-20))) } catch { /* ignore */ }
}

function deleteSnapshot(index) {
  const snapshots = loadSnapshots()
  snapshots.splice(index, 1)
  try { localStorage.setItem(SNAPSHOTS_KEY, JSON.stringify(snapshots)) } catch { /* ignore */ }
}

export default function AnimeLofiStudio() {
  const saved = loadSavedState()

  const [activeStep, setActiveStep] = useState(saved?.activeStep ?? 0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const [userIdea, setUserIdea] = useState(saved?.userIdea ?? "")
  const [segments, setSegments] = useState(saved?.segments ?? [])
  const [fullScript, setFullScript] = useState(saved?.fullScript ?? "")

  const [audioInfo, setAudioInfo] = useState(saved?.audioInfo ?? null)

  const [images, setImages] = useState(saved?.images ?? [])
  const [imageProgress, setImageProgress] = useState(null)
  const pollRef = useRef(null)

  const [videos, setVideos] = useState(saved?.videos ?? [])
  const [videoProgress, setVideoProgress] = useState(null)
  const videoPollRef = useRef(null)
  // Track multiple retry polls: { [index]: { job_id, interval } }
  const retryPollsRef = useRef({})
  const retryImagePollsRef = useRef({})

  const [finalVideo, setFinalVideo] = useState(saved?.finalVideo ?? null)
  const [renderLoading, setRenderLoading] = useState(false)
  const [renderError, setRenderError] = useState(null)

  // Resume / snapshot state
  const [showResumeBanner, setShowResumeBanner] = useState(!!saved)
  const [snapshotOpen, setSnapshotOpen] = useState(false)
  const [loadOpen, setLoadOpen] = useState(false)
  const [snapshots, setSnapshots] = useState(loadSnapshots())

  const stopPolling = (ref) => {
    if (ref.current) { clearInterval(ref.current); ref.current = null }
  }

  // Stop all retry polls
  const stopRetryPolls = () => {
    Object.values(retryPollsRef.current).forEach(({ interval }) => clearInterval(interval))
    retryPollsRef.current = {}
  }

  const stopRetryImagePolls = () => {
    Object.values(retryImagePollsRef.current).forEach(({ interval }) => clearInterval(interval))
    retryImagePollsRef.current = {}
  }

  // Persist state on every relevant change
  useEffect(() => {
    saveState({ activeStep, userIdea, segments, fullScript, audioInfo, images, videos, finalVideo })
  }, [activeStep, userIdea, segments, fullScript, audioInfo, images, videos, finalVideo])

  useEffect(() => {
    return () => { stopPolling(pollRef); stopPolling(videoPollRef); stopRetryPolls(); stopRetryImagePolls() }
  }, [])

  // ── Step 0: Script ────────────────────────────────────────────

  const handleGenerateScript = async () => {
    if (!userIdea.trim()) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/anime-lofi/generate-script", { user_idea: userIdea })
      setSegments(res.data.segments || [])
      setFullScript(res.data.full_script || "")
    } catch (e) { setError(e.response?.data?.detail || "Script gen failed") }
    finally { setLoading(false) }
  }

  // ── Step 1: Audio ─────────────────────────────────────────────

  const handleGenerateAudio = async () => {
    if (!fullScript) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/anime-lofi/generate-audio", { script: fullScript })
      setAudioInfo(res.data)
    } catch (e) { setError(e.response?.data?.detail || "Audio gen failed") }
    finally { setLoading(false) }
  }

  // ── Step 2: Transcribe + Images ───────────────────────────────

  const handleTranscribeAndGenerateImages = async () => {
    if (!audioInfo || !segments.length) return
    setLoading(true); setError(null)
    setImageProgress({ current: 0, total: segments.length, step: "Transcribing audio…" })
    stopPolling(pollRef)

    try {
      // 1. Transcribe & align to get per-segment durations
      const transRes = await http.post("/api/anime-lofi/transcribe-and-align", {
        audio_filename: audioInfo.filename,
        script: fullScript,
        segments,
      })
      const alignedSegments = transRes.data.segments || segments
      setSegments(alignedSegments)

      // 2. Start async image generation
      const imgRes = await http.post("/api/anime-lofi/generate-images-async", { segments: alignedSegments })
      const jobId = imgRes.data.job_id
      if (!jobId) throw new Error("No job_id returned")

      // 3. Poll for completion
      await new Promise((resolve, reject) => {
        pollRef.current = setInterval(async () => {
          try {
            const { data } = await http.get(`/api/anime-lofi/generate-images-status/${jobId}`)
            if (data.status === "success") {
              stopPolling(pollRef)
              setImages(data.images || [])
              setImageProgress(null)
              resolve()
            } else if (data.status === "failed") {
              stopPolling(pollRef)
              reject(new Error(data.error_message || "Image generation failed"))
            } else {
              const pct = data.progress_pct || 0
              const done = Math.round(pct / 100 * segments.length)
              setImageProgress({ current: Math.min(done, segments.length), total: segments.length, step: data.current_step || "Generating…" })
            }
          } catch (pollErr) { /* keep polling */ }
        }, 2000)
      })
    } catch (e) {
      stopPolling(pollRef)
      setImageProgress(null)
      setError(e.message || "Image gen failed")
    } finally {
      setLoading(false)
    }
  }

  // ── Step 3: Videos ────────────────────────────────────────────

  const handleGenerateVideos = async () => {
    if (!images.length || !segments.length) return
    setLoading(true); setError(null)
    setVideoProgress({ current: 0, total: images.length, step: "Starting…" })
    stopPolling(videoPollRef)

    try {
      const res = await http.post("/api/anime-lofi/generate-videos-async", { images, segments })
      const jobId = res.data.job_id
      if (!jobId) throw new Error("No job_id returned")

      await new Promise((resolve, reject) => {
        videoPollRef.current = setInterval(async () => {
          try {
            const { data } = await http.get(`/api/anime-lofi/generate-videos-status/${jobId}`)
            if (data.status === "success") {
              stopPolling(videoPollRef)
              setVideos(data.videos || [])
              setVideoProgress(null)
              resolve()
            } else if (data.status === "failed") {
              stopPolling(videoPollRef)
              reject(new Error(data.error_message || "Video generation failed"))
            } else {
              const pct = data.progress_pct || 0
              const done = Math.round(pct / 100 * images.length)
              setVideoProgress({ current: Math.min(done, images.length), total: images.length, step: data.current_step || "Generating…" })
            }
          } catch (pollErr) { /* keep polling */ }
        }, 2000)
      })
    } catch (e) {
      stopPolling(videoPollRef)
      setVideoProgress(null)
      setError(e.message || "Video gen failed")
    } finally {
      setLoading(false)
    }
  }

  const handleRetryVideo = async (index) => {
    if (!images[index] || !segments[index]) return
    setError(null)

    try {
      const res = await http.post("/api/anime-lofi/retry-video", {
        image: images[index],
        segment: segments[index],
      })
      const jobId = res.data.job_id
      if (!jobId) return

      // Mark this segment as retrying
      setVideos((prev) => {
        const next = [...prev]
        if (next[index]) next[index] = { ...next[index], retrying: true }
        return next
      })

      // Start polling this retry job
      const interval = setInterval(async () => {
        try {
          const { data } = await http.get(`/api/anime-lofi/generate-videos-status/${jobId}`)
          if (data.status === "success") {
            clearInterval(interval)
            delete retryPollsRef.current[index]
            const retried = (data.videos || [])[0]
            if (retried) {
              retried.retrying = false
              setVideos((prev) => {
                const next = [...prev]
                next[index] = retried
                return next
              })
            }
          } else if (data.status === "failed") {
            clearInterval(interval)
            delete retryPollsRef.current[index]
            setVideos((prev) => {
              const next = [...prev]
              if (next[index]) next[index] = { ...next[index], retrying: false }
              return next
            })
            setError(`Video ${index + 1} retry failed: ${data.error_message || "Unknown error"}`)
          }
        } catch { /* keep polling */ }
      }, 2000)
      retryPollsRef.current[index] = { job_id, interval }
    } catch (e) {
      setError(e.message || "Retry failed")
    }
  }

  const handleRetryImage = async (index) => {
    if (!segments[index]) return
    setError(null)

    try {
      const res = await http.post("/api/anime-lofi/retry-image", {
        segment: segments[index],
      })
      const jobId = res.data.job_id
      if (!jobId) return

      // Mark this segment as retrying
      setImages((prev) => {
        const next = [...prev]
        if (next[index]) next[index] = { ...next[index], retrying: true }
        return next
      })

      const interval = setInterval(async () => {
        try {
          const { data } = await http.get(`/api/anime-lofi/generate-images-status/${jobId}`)
          if (data.status === "success") {
            clearInterval(interval)
            delete retryImagePollsRef.current[index]
            const retried = (data.images || [])[0]
            if (retried) {
              retried.retrying = false
              setImages((prev) => {
                const next = [...prev]
                next[index] = retried
                return next
              })
            }
          } else if (data.status === "failed") {
            clearInterval(interval)
            delete retryImagePollsRef.current[index]
            setImages((prev) => {
              const next = [...prev]
              if (next[index]) next[index] = { ...next[index], retrying: false }
              return next
            })
            setError(`Image ${index + 1} retry failed: ${data.error_message || "Unknown error"}`)
          }
        } catch { /* keep polling */ }
      }, 2000)
      retryImagePollsRef.current[index] = { job_id, interval }
    } catch (e) {
      setError(e.message || "Retry failed")
    }
  }

  // ── Step 4: Compilation ───────────────────────────────────────

  const handleRenderFinal = async () => {
    if (!videos.length || !audioInfo) return
    setRenderLoading(true); setRenderError(null); setError(null)
    try {
      const res = await http.post("/api/anime-lofi/render-video-compilation", {
        videos,
        audio_filename: audioInfo.filename,
      })
      setFinalVideo(res.data)
    } catch (e) { setRenderError(e.response?.data?.detail || "Render failed") }
    finally { setRenderLoading(false) }
  }

  // ── Snapshot helpers ──────────────────────────────────────────

  const handleSaveSnapshot = useCallback(() => {
    const label = `Session ${new Date().toLocaleString()}`
    saveSnapshot({ activeStep, userIdea, segments, fullScript, audioInfo, images, videos, finalVideo }, label)
    setSnapshots(loadSnapshots())
  }, [activeStep, userIdea, segments, fullScript, audioInfo, images, videos, finalVideo])

  const handleLoadSnapshot = useCallback((snap) => {
    const s = snap.state
    setActiveStep(s.activeStep ?? 0)
    setUserIdea(s.userIdea ?? "")
    setSegments(s.segments ?? [])
    setFullScript(s.fullScript ?? "")
    setAudioInfo(s.audioInfo ?? null)
    setImages(s.images ?? [])
    setVideos(s.videos ?? [])
    setFinalVideo(s.finalVideo ?? null)
    setLoadOpen(false)
  }, [])

  const handleDeleteSnapshot = useCallback((index) => {
    deleteSnapshot(index)
    setSnapshots(loadSnapshots())
  }, [])

  // ── Render ────────────────────────────────────────────────────

  return (
    <Box sx={{ height: "100%", overflow: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1200, mx: "auto" }}>
        <Paper variant="outlined" sx={{
          p: 2.5, borderRadius: 3,
          background: (t) => t.palette.mode === "dark"
            ? "linear-gradient(135deg, rgba(100,149,237,0.15) 0%, rgba(15,23,42,1) 70%)"
            : "linear-gradient(135deg, rgba(100,149,237,0.10) 0%, rgba(255,255,255,1) 70%)",
        }}>
          <Stack spacing={1}>
            <Chip icon={<AutoAwesomeIcon sx={{ fontSize: 16 }} />} label="Lo-Fi Anime Shorts" color="primary" variant="outlined" sx={{ width: "fit-content" }} />
            <Stack direction="row" justifyContent="space-between" alignItems="center">
              <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.6 }}>Studio</Typography>
              <Stack direction="row" spacing={0.5}>
                <Tooltip title="Save current session">
                  <IconButton size="small" onClick={handleSaveSnapshot}><SaveIcon fontSize="small" /></IconButton>
                </Tooltip>
                <Tooltip title="Load a saved session">
                  <IconButton size="small" onClick={() => setLoadOpen(true)}><FolderOpenIcon fontSize="small" /></IconButton>
                </Tooltip>
              </Stack>
            </Stack>
            <Typography sx={{ color: "text.secondary", maxWidth: 700 }}>
              Describe a theme or feeling. The AI writes a poetic script, generates images with Z-turbo, and animates each segment with LTX video.
            </Typography>
          </Stack>
        </Paper>

        {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

        {/* Resume banner */}
        {showResumeBanner && (
          <Alert severity="info" icon={<FolderOpenIcon />}
            action={
              <Stack direction="row" spacing={1}>
                <Button size="small" color="inherit" onClick={() => setShowResumeBanner(false)}>Resume</Button>
                <Button size="small" color="inherit" onClick={() => { clearSavedState(); setShowResumeBanner(false); window.location.reload() }}>
                  Start Fresh
                </Button>
              </Stack>
            }
            sx={{ "& .MuiAlert-action": { pt: 0 } }}
          >
            You have a saved session from earlier.
          </Alert>
        )}

        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, minWidth: 220, alignSelf: "flex-start" }}>
            <Stepper activeStep={activeStep} orientation="vertical" sx={{ "& .MuiStepConnector-root": { ml: 1.5 } }}>
              {STEPS.map((s, i) => (
                <Step key={s.label} completed={i < activeStep} onClick={() => i < activeStep && setActiveStep(i)}
                  sx={{ cursor: i < activeStep ? "pointer" : "default" }}>
                  <StepLabel
                    StepIconComponent={() => (
                      <Box sx={{
                        width: 32, height: 32, borderRadius: "50%",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        bgcolor: i < activeStep ? "primary.main" : i === activeStep ? "primary.light" : "action.disabledBackground",
                        color: i <= activeStep ? "#fff" : "text.disabled", fontSize: 16,
                      }}>{s.icon}</Box>
                    )}
                    sx={{
                      "& .MuiStepLabel-labelContainer": { ml: 1.5 },
                      "& .MuiStepLabel-label": {
                        fontWeight: i === activeStep ? 700 : 400,
                        color: i <= activeStep ? "text.primary" : "text.disabled",
                      },
                    }}
                  >{s.label}</StepLabel>
                </Step>
              ))}
            </Stepper>
          </Paper>

          <Paper variant="outlined" sx={{ p: 3, borderRadius: 3, minHeight: 400, flex: 1 }}>

            {/* Step 0: User idea → structured segments */}
            {activeStep === 0 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>1. Describe Your Theme</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Describe a feeling, place, or idea. The AI writes a 40-65 word poetic script and splits it into 3-5 visual segments.
                </Typography>
                <TextField label="Your idea / theme"
                  placeholder="e.g. The quiet loneliness of waiting for a train at midnight in a small coastal town"
                  value={userIdea} onChange={(e) => setUserIdea(e.target.value)}
                  multiline minRows={3} maxRows={5} />
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button variant="contained" onClick={handleGenerateScript} disabled={loading || !userIdea.trim()}
                    startIcon={loading ? <CircularProgress size={18} /> : <AutoAwesomeIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                    {loading ? "Generating..." : "Generate Script"}
                  </Button>
                </Stack>
                {segments.length > 0 && (
                  <>
                    <Typography variant="subtitle2" sx={{ fontWeight: 600, mt: 1 }}>
                      Segments ({segments.length})
                    </Typography>
                    {segments.map((seg) => (
                      <Paper key={seg.scene_number} variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
                        <Stack direction="row" spacing={1.5} alignItems="flex-start">
                          <Chip label={`#${seg.scene_number}`} size="small" color="primary" variant="outlined" sx={{ mt: 0.3, minWidth: 44 }} />
                          <Box sx={{ flex: 1 }}>
                            <Typography sx={{ fontWeight: 600, mb: 0.5 }}>"{seg.voiceover}"</Typography>
                            <Typography variant="body2" sx={{ color: "text.secondary", fontSize: 13 }}>
                              Scene: {seg.scene_description}
                            </Typography>
                          </Box>
                        </Stack>
                      </Paper>
                    ))}
                    <Button variant="contained" onClick={() => setActiveStep(1)}
                      sx={{ alignSelf: "flex-start", borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      Looks good, continue
                    </Button>
                  </>
                )}
              </Stack>
            )}

            {/* Step 1: Audio */}
            {activeStep === 1 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>2. Generate Audio</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Convert the full script to speech.
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button variant="contained" onClick={handleGenerateAudio} disabled={loading}
                    startIcon={loading ? <CircularProgress size={18} /> : <MusicNoteIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                    {loading ? "Generating..." : "Generate Audio"}
                  </Button>
                </Stack>
                {audioInfo && (
                  <>
                    <audio controls src={audioInfo.url} style={{ width: "100%", maxWidth: 400 }} />
                    <Button variant="contained" onClick={() => setActiveStep(2)}
                      sx={{ alignSelf: "flex-start", borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      Continue
                    </Button>
                  </>
                )}
              </Stack>
            )}

            {/* Step 2: Transcribe + Generate Images */}
            {activeStep === 2 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>3. Create Images</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Transcribe audio to get per-segment timing, then generate one image per segment.
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap">
                  {!imageProgress ? (
                    <Button variant="contained" onClick={handleTranscribeAndGenerateImages} disabled={loading || images.length > 0}
                      startIcon={loading ? <CircularProgress size={18} /> : <ImageIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      {loading ? "Transcribing…" : `Transcribe & Generate ${segments.length} Images`}
                    </Button>
                  ) : (
                    <Stack direction="row" spacing={1.5} alignItems="center">
                      <CircularProgress size={20} />
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {imageProgress.step} ({imageProgress.current}/{imageProgress.total})
                      </Typography>
                    </Stack>
                  )}
                  {images.length > 0 && !imageProgress && <Chip icon={<CheckCircleIcon />} label="Done" color="success" variant="outlined" />}
                </Stack>
                {imageProgress && (
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    This may take a few minutes. The pod generates one image at a time.
                  </Typography>
                )}
                {images.length > 0 && (
                  <Grid container spacing={1.5}>
                    {images.map((img) => {
                      const seg = segments[img.index]
                      return (
                        <Grid item xs={6} key={img.index}>
                          <Card variant="outlined" sx={{ maxWidth: 320, position: "relative" }}>
                            {img.retrying ? (
                              <Box sx={{ width: "100%", aspectRatio: "9/16", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "action.hover" }}>
                                <CircularProgress size={24} />
                              </Box>
                            ) : (
                              <CardMedia component="img" image={img.url} alt={img.segment_text}
                                sx={{ width: "100%", aspectRatio: "9/16", objectFit: "cover" }} />
                            )}
                            <Box sx={{ p: 1 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center">
                                <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
                                  #{seg?.scene_number || img.index + 1} {seg?.duration_sec ? `(${seg.duration_sec}s)` : ""}
                                </Typography>
                                <Tooltip title="Retry this image">
                                  <IconButton size="small" onClick={() => handleRetryImage(img.index)} disabled={img.retrying}>
                                    <ReplayIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </Stack>
                              <Typography variant="caption" sx={{
                                display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden",
                              }}>
                                {img.segment_text}
                              </Typography>
                            </Box>
                          </Card>
                        </Grid>
                      )
                    })}
                  </Grid>
                )}
                {images.length > 0 && (
                  <Button variant="contained" onClick={() => setActiveStep(3)}
                    sx={{ alignSelf: "flex-start", borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                    Looks good, continue
                  </Button>
                )}
              </Stack>
            )}

            {/* Step 3: Generate Segment Videos */}
            {activeStep === 3 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>4. Generate Segment Videos</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Generate one LTX video per segment — each animated from its image.
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center">
                  {!videoProgress && videos.length === 0 ? (
                    <Button variant="contained" onClick={handleGenerateVideos} disabled={loading}
                      startIcon={loading ? <CircularProgress size={18} /> : <VideocamIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      {loading ? "Starting…" : `Generate ${images.length} Videos`}
                    </Button>
                  ) : videoProgress ? (
                    <Stack direction="row" spacing={1.5} alignItems="center">
                      <CircularProgress size={20} />
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>
                        {videoProgress.step} ({videoProgress.current}/{videoProgress.total})
                      </Typography>
                    </Stack>
                  ) : null}
                  {videos.length > 0 && !videoProgress && <Chip icon={<CheckCircleIcon />} label="Videos done" color="success" variant="outlined" />}
                </Stack>
                {videos.length > 0 && (
                  <Grid container spacing={1.5}>
                    {videos.map((vid) => {
                      const seg = segments[vid.index]
                      return (
                        <Grid item xs={6} key={vid.index}>
                          <Card variant="outlined" sx={{ maxWidth: 320, position: "relative" }}>
                            {vid.retrying ? (
                              <Box sx={{ width: "100%", aspectRatio: "9/16", display: "flex", alignItems: "center", justifyContent: "center", bgcolor: "action.hover" }}>
                                <CircularProgress size={24} />
                              </Box>
                            ) : (
                              <video src={vid.url} style={{ width: "100%", aspectRatio: "9/16", objectFit: "cover", display: "block" }} controls />
                            )}
                            <Box sx={{ p: 1 }}>
                              <Stack direction="row" justifyContent="space-between" alignItems="center">
                                <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600 }}>
                                  #{seg?.scene_number || vid.index + 1} ({vid.duration?.toFixed(1) || "?"}s)
                                </Typography>
                                <Tooltip title="Retry this segment">
                                  <IconButton size="small" onClick={() => handleRetryVideo(vid.index)} disabled={vid.retrying}>
                                    <ReplayIcon fontSize="small" />
                                  </IconButton>
                                </Tooltip>
                              </Stack>
                              <Typography variant="caption" sx={{
                                display: "-webkit-box", WebkitLineClamp: 1, WebkitBoxOrient: "vertical", overflow: "hidden",
                              }}>
                                {vid.video_prompt || vid.segment_text}
                              </Typography>
                            </Box>
                          </Card>
                        </Grid>
                      )
                    })}
                  </Grid>
                )}
                {videos.length > 0 && !videoProgress && (
                  <Stack direction="row" spacing={2}>
                    <Button variant="outlined" onClick={handleGenerateVideos} disabled={loading}
                      startIcon={loading ? <CircularProgress size={18} /> : <ReplayIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      Regenerate All
                    </Button>
                    <Button variant="contained" onClick={() => setActiveStep(4)}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                      Looks good, continue
                    </Button>
                  </Stack>
                )}
              </Stack>
            )}

            {/* Step 4: Compilation */}
            {activeStep === 4 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>5. Render Final Video</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Stitch the segment videos with the audio track into the final lo-fi anime short.
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button variant="contained" onClick={handleRenderFinal} disabled={renderLoading}
                    startIcon={renderLoading ? <CircularProgress size={18} /> : <VideocamIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                    {renderLoading ? "Rendering..." : finalVideo ? "Re-render" : "Render Final Video"}
                  </Button>
                </Stack>
                {renderError && (
                  <Stack direction="row" spacing={1.5} alignItems="center">
                    <Alert severity="error" onClose={() => setRenderError(null)} sx={{ flex: 1 }}>{renderError}</Alert>
                    <Button variant="outlined" onClick={handleRenderFinal} disabled={renderLoading}
                      startIcon={<ReplayIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none", whiteSpace: "nowrap" }}>
                      Retry
                    </Button>
                  </Stack>
                )}
                {finalVideo && (
                  <Stack spacing={2}>
                    <Chip icon={<CheckCircleIcon />} label="Final video ready!" color="success" sx={{ width: "fit-content" }} />
                    <video controls src={finalVideo.url} style={{ width: "100%", maxWidth: 400, borderRadius: 8 }} />
                    <Stack direction="row" spacing={1.5}>
                      <Button variant="outlined" onClick={handleRenderFinal} disabled={renderLoading}
                        startIcon={<ReplayIcon />}
                        sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                        Re-render
                      </Button>
                      <Button variant="contained" onClick={() => {
                        clearSavedState()
                        setUserIdea(""); setFullScript(""); setSegments([])
                        setAudioInfo(null); setImages([]); setVideos([])
                        setFinalVideo(null); setActiveStep(0)
                      }} sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}>
                        Create Another
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Stack>
            )}

          </Paper>
        </Stack>
      </Stack>

      {/* Load Snapshot dialog */}
      <Dialog open={loadOpen} onClose={() => setLoadOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Saved Sessions</DialogTitle>
        <DialogContent>
          {snapshots.length === 0 ? (
            <Typography variant="body2" sx={{ color: "text.secondary", py: 2 }}>
              No saved sessions yet. Use the <SaveIcon sx={{ verticalAlign: "middle", fontSize: 18 }} /> button to save one.
            </Typography>
          ) : (
            <List dense>
              {[...snapshots].reverse().map((snap, i) => {
                const idx = snapshots.length - 1 - i
                const steps = snap.state.activeStep ?? 0
                const segs = snap.state.segments?.length ?? 0
                const hasVids = (snap.state.videos?.length ?? 0) > 0
                return (
                  <ListItemButton key={idx} onClick={() => handleLoadSnapshot(snap)}
                    sx={{ borderRadius: 1, mb: 0.5, border: "1px solid", borderColor: "divider" }}>
                    <ListItemText
                      primary={snap.label}
                      secondary={`Step ${steps + 1} · ${segs} segments${hasVids ? " · videos ready" : ""}`}
                      primaryTypographyProps={{ fontWeight: 600 }}
                    />
                    <IconButton edge="end" size="small" onClick={(e) => { e.stopPropagation(); handleDeleteSnapshot(idx) }}
                      sx={{ ml: 1, opacity: 0.4, "&:hover": { opacity: 1 } }}>
                      <ReplayIcon fontSize="small" />
                    </IconButton>
                  </ListItemButton>
                )
              })}
            </List>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoadOpen(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
