import { useState, useEffect, useRef } from "react"
import {
  Box, Stack, Typography, Paper, Button, CircularProgress,
  Stepper, Step, StepLabel, Chip, Card, CardMedia,
  TextField, MenuItem,
  Alert, Grid, IconButton, Tooltip,
} from "@mui/material"
import http from "../api/http"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import CheckCircleIcon from "@mui/icons-material/CheckCircle"
import PlayArrowIcon from "@mui/icons-material/PlayArrow"
import MusicNoteIcon from "@mui/icons-material/MusicNote"
import ImageIcon from "@mui/icons-material/Image"
import VideocamIcon from "@mui/icons-material/Videocam"

const STEPS = [
  { label: "Select & Generate Image", icon: <ImageIcon /> },
  { label: "Generate Script", icon: <AutoAwesomeIcon /> },
  { label: "Generate Audio", icon: <MusicNoteIcon /> },
  { label: "Lip-sync Video", icon: <VideocamIcon /> },
  { label: "Finalize", icon: <CheckCircleIcon /> },
]

function StepPreview({ stepIndex, generatedImage, generatedScript, generatedAudio, generatedVideo, finalVideo }) {
  const src = [null, generatedImage, generatedScript, generatedAudio, generatedVideo, finalVideo][stepIndex]
  if (!src) return null
  if (stepIndex === 2) return null
  if (stepIndex === 3) return null
  const isVideo = stepIndex >= 4
  if (isVideo) {
    return (
      <video
        src={typeof src === "object" ? src.url || `/api/niche1/media/${src.filename}` : src}
        style={{ width: 48, height: 48, borderRadius: 6, objectFit: "cover", marginLeft: 8 }}
        muted
      />
    )
  }
  const imgSrc = typeof src === "object" ? src.url || `/api/niche1/media/${src.filename}` : null
  if (!imgSrc) return null
  return (
    <Box
      component="img"
      src={imgSrc}
      sx={{ width: 48, height: 48, borderRadius: 6, objectFit: "cover", ml: 1 }}
    />
  )
}

export default function Niche1Studio() {
  const [activeStep, setActiveStep] = useState(0)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [history, setHistory] = useState(null)

  const [baseImages, setBaseImages] = useState([])
  const [selectedBase, setSelectedBase] = useState(null)
  const [topics, setTopics] = useState([])
  const [selectedTopic, setSelectedTopic] = useState("")
  const [scratchNotes, setScratchNotes] = useState("")
  const [generatedImage, setGeneratedImage] = useState(null)
  const [generatedScript, setGeneratedScript] = useState(null)
  const [generatedAudio, setGeneratedAudio] = useState(null)
  const [generatedVideo, setGeneratedVideo] = useState(null)
  const [finalVideo, setFinalVideo] = useState(null)

  const videoRef = useRef(null)

  useEffect(() => { fetchBaseImages(); fetchTopics(); fetchHistory() }, [])

  const fetchBaseImages = async () => {
    try {
      const res = await http.get("/api/niche1/base-images")
      setBaseImages(res.data.images || [])
    } catch { setBaseImages([]) }
  }

  const fetchTopics = async () => {
    try {
      const res = await http.get("/api/niche1/topics")
      setTopics(res.data.topics || [])
    } catch { setTopics([]) }
  }

  const fetchHistory = async () => {
    try {
      const res = await http.get("/api/niche1/history")
      setHistory(res.data)
    } catch {}
  }

  const handleGenerateImage = async () => {
    if (!selectedBase) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/niche1/generate-image", {
        base_filename: selectedBase.filename,
        description: "",
      })
      setGeneratedImage(res.data)
    } catch (e) { setError(e.response?.data?.detail || "Image gen failed") }
    finally { setLoading(false) }
  }

  const handleGenerateScript = async () => {
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/niche1/generate-script", {
        topic: selectedTopic || undefined,
        custom_instructions: scratchNotes || undefined,
      })
      setGeneratedScript(res.data)
    } catch (e) { setError(e.response?.data?.detail || "Script gen failed") }
    finally { setLoading(false) }
  }

  const handleGenerateAudio = async () => {
    if (!generatedScript) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/niche1/generate-audio", {
        script: generatedScript.script,
      })
      setGeneratedAudio(res.data)
    } catch (e) { setError(e.response?.data?.detail || "Audio gen failed") }
    finally { setLoading(false) }
  }

  const handleGenerateVideo = async () => {
    if (!generatedImage || !generatedAudio) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/niche1/generate-video", {
        image_filename: generatedImage.filename,
        audio_filename: generatedAudio.filename,
      })
      setGeneratedVideo(res.data)
    } catch (e) { setError(e.response?.data?.detail || "Lip-sync failed") }
    finally { setLoading(false) }
  }

  const handleFinalize = async () => {
    if (!generatedVideo) return
    setLoading(true); setError(null)
    try {
      const res = await http.post("/api/niche1/finalize", {
        video_filename: generatedVideo.filename,
        script: generatedScript?.script || "",
      })
      setFinalVideo(res.data)
      fetchHistory()
    } catch (e) { setError(e.response?.data?.detail || "Finalize failed") }
    finally { setLoading(false) }
  }

  const stepData = [null, generatedImage, generatedScript, generatedAudio, generatedVideo, finalVideo]

  return (
    <Box sx={{ height: "100%", overflow: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1200, mx: "auto" }}>
        <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3,
          background: (t) => t.palette.mode === "dark"
            ? "linear-gradient(135deg, rgba(201,100,66,0.15) 0%, rgba(15,23,42,1) 70%)"
            : "linear-gradient(135deg, rgba(201,100,66,0.10) 0%, rgba(255,255,255,1) 70%)",
        }}>
          <Stack spacing={1}>
            <Chip icon={<AutoAwesomeIcon sx={{ fontSize: 16 }} />} label="Podcast Quote Shorts" color="primary" variant="outlined" sx={{ width: "fit-content" }} />
            <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.6 }}>
              Studio
            </Typography>
            <Typography sx={{ color: "text.secondary", maxWidth: 700 }}>
              Step-by-step: pick a base image, generate a variation and script, then produce a lip-sync video with captions and music.
            </Typography>
          </Stack>
        </Paper>

        {error && <Alert severity="error" onClose={() => setError(null)}>{error}</Alert>}

        <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
          {/* Vertical Stepper */}
          <Paper variant="outlined" sx={{ p: 2, borderRadius: 3, minWidth: 260, alignSelf: "flex-start" }}>
            <Stepper activeStep={activeStep} orientation="vertical" sx={{ "& .MuiStepConnector-root": { ml: 1.5 } }}>
              {STEPS.map((s, i) => (
                <Step key={s.label} completed={i < activeStep} onClick={() => i < activeStep && setActiveStep(i)} sx={{ cursor: i < activeStep ? "pointer" : "default" }}>
                  <StepLabel
                    StepIconComponent={() => (
                      <Stack direction="row" alignItems="center">
                        <Box sx={{
                          width: 32, height: 32, borderRadius: "50%",
                          display: "flex", alignItems: "center", justifyContent: "center",
                          bgcolor: i < activeStep ? "primary.main" : i === activeStep ? "primary.light" : "action.disabledBackground",
                          color: i <= activeStep ? "#fff" : "text.disabled",
                          fontSize: 16,
                        }}>{s.icon}</Box>
                      </Stack>
                    )}
                    sx={{
                      "& .MuiStepLabel-labelContainer": { ml: 1.5 },
                      "& .MuiStepLabel-label": {
                        fontWeight: i === activeStep ? 700 : 400,
                        color: i <= activeStep ? "text.primary" : "text.disabled",
                        display: "flex", alignItems: "center", gap: 1,
                      },
                    }}
                  >
                    {s.label}
                    {i < activeStep && (
                      <StepPreview
                        stepIndex={i + 1}
                        generatedImage={generatedImage}
                        generatedScript={generatedScript}
                        generatedAudio={generatedAudio}
                        generatedVideo={generatedVideo}
                        finalVideo={finalVideo}
                      />
                    )}
                  </StepLabel>
                </Step>
              ))}
            </Stepper>
          </Paper>

          {/* Step Content */}
          <Paper variant="outlined" sx={{ p: 3, borderRadius: 3, minHeight: 400, flex: 1 }}>
            {/* Step 0: Select base image + generate variation */}
            {activeStep === 0 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>1. Select & Generate Image</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Pick a base photo, then generate an AI variation with slight stylistic changes.
                </Typography>
                {baseImages.length === 0 ? (
                  <Alert severity="info">
                    No base images found. Add images to <code>storage/niche1/base/</code> folder.
                  </Alert>
                ) : (
                  <Grid container spacing={1.5}>
                    {baseImages.map((img) => (
                      <Grid item xs={4} sm={3} md={2} key={img.filename}>
                        <Card
                          variant="outlined"
                          sx={{
                            cursor: "pointer",
                            width: 160,
                            border: selectedBase?.filename === img.filename ? 2 : 1,
                            borderColor: selectedBase?.filename === img.filename ? "primary.main" : "divider",
                            transition: "all 0.15s",
                            "&:hover": { transform: "scale(1.02)" },
                          }}
                          onClick={() => setSelectedBase(img)}
                        >
                          <CardMedia
                            component="img"
                            image={img.url}
                            alt={img.filename}
                            sx={{ width: 160, height: 210, objectFit: "cover" }}
                          />
                        </Card>
                      </Grid>
                    ))}
                  </Grid>
                )}
                {selectedBase && (
                  <Stack direction="row" spacing={2} alignItems="center" sx={{ mt: 1 }}>
                    <Button
                      variant="contained"
                      onClick={handleGenerateImage}
                      disabled={loading}
                      startIcon={loading ? <CircularProgress size={18} /> : <AutoAwesomeIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                    >
                      {loading ? "Generating..." : "Generate Variation"}
                    </Button>
                    {generatedImage && <Chip icon={<CheckCircleIcon />} label="Done" color="success" variant="outlined" />}
                  </Stack>
                )}
                {generatedImage && (
                  <Box>
                    <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 600 }}>Variation preview:</Typography>
                    <Card variant="outlined" sx={{ maxWidth: 240 }}>
                      <CardMedia
                        component="img"
                        image={generatedImage.url}
                        sx={{ aspectRatio: "3/4", objectFit: "cover" }}
                      />
                    </Card>
                  </Box>
                )}
                {generatedImage && activeStep === 0 && (
                  <Button
                    variant="contained"
                    onClick={() => setActiveStep(1)}
                    sx={{ alignSelf: "flex-start", borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                  >
                    Looks good, continue
                  </Button>
                )}
              </Stack>
            )}

            {/* Step 1: Script Generation */}
            {activeStep === 1 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>2. Generate Script</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Choose a topic or let the system pick one. The AI will write a short emotional quote script. You can also jot down scratch notes to steer the tone or angle.
                </Typography>
                <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap" }}>
                  <TextField
                    select
                    label="Topic (optional)"
                    value={selectedTopic}
                    onChange={(e) => setSelectedTopic(e.target.value)}
                    sx={{ maxWidth: 300 }}
                    size="small"
                  >
                    <MenuItem value="">Random</MenuItem>
                    {topics.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                  <TextField
                    label="Scratch notes (optional)"
                    placeholder="e.g. Make it about resilience after breakup, raw and emotional..."
                    value={scratchNotes}
                    onChange={(e) => setScratchNotes(e.target.value)}
                    multiline
                    minRows={2}
                    maxRows={4}
                    sx={{ minWidth: 300, flex: 1 }}
                    size="small"
                  />
                </Stack>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button
                    variant="contained"
                    onClick={handleGenerateScript}
                    disabled={loading}
                    startIcon={loading ? <CircularProgress size={18} /> : <AutoAwesomeIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                  >
                    {loading ? "Generating..." : "Generate Script"}
                  </Button>
                </Stack>
                {generatedScript && (
                  <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, bgcolor: "action.hover" }}>
                    <Typography variant="subtitle2" sx={{ mb: 1, color: "text.secondary" }}>
                      Script ({generatedScript.topic}):
                    </Typography>
                    <Typography sx={{ whiteSpace: "pre-wrap", lineHeight: 1.8 }}>
                      {generatedScript.script}
                    </Typography>
                    <Button
                      variant="contained"
                      onClick={() => setActiveStep(2)}
                      sx={{ mt: 1.5, borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                    >
                      Looks good, continue
                    </Button>
                  </Paper>
                )}
              </Stack>
            )}

            {/* Step 2: Audio Generation */}
            {activeStep === 2 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>3. Generate Audio</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Convert the script to speech using AI voiceover.
                </Typography>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button
                    variant="contained"
                    onClick={handleGenerateAudio}
                    disabled={loading}
                    startIcon={loading ? <CircularProgress size={18} /> : <MusicNoteIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                  >
                    {loading ? "Generating..." : "Generate Audio"}
                  </Button>
                </Stack>
                {generatedAudio && (
                  <Stack spacing={1.5}>
                    <Chip icon={<CheckCircleIcon />} label="Audio ready" color="success" variant="outlined" sx={{ width: "fit-content" }} />
                    <audio controls src={generatedAudio.url} style={{ width: "100%", maxWidth: 400 }} />
                    <Button
                      variant="contained"
                      onClick={() => setActiveStep(3)}
                      sx={{ alignSelf: "flex-start", borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                    >
                      Continue
                    </Button>
                  </Stack>
                )}
              </Stack>
            )}

            {/* Step 3: Lip-sync Video */}
            {activeStep === 3 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>4. Generate Lip-sync Video</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Send the image and audio to RunPod ComfyUI to generate a talking head video. This takes 1-5 minutes.
                </Typography>
                <Alert severity="info">
                  Make sure your RunPod pod is deployed and ready. Go to <strong>ComfyUI Setup</strong> to check.
                </Alert>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Button
                    variant="contained"
                    onClick={handleGenerateVideo}
                    disabled={loading}
                    startIcon={loading ? <CircularProgress size={18} /> : <VideocamIcon />}
                    sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                  >
                    {loading ? "Generating (1-5 min)..." : "Generate Video"}
                  </Button>
                </Stack>
                {generatedVideo && (
                  <Stack spacing={1.5}>
                    <Chip icon={<CheckCircleIcon />} label="Video ready" color="success" variant="outlined" sx={{ width: "fit-content" }} />
                    <video
                      ref={videoRef}
                      controls
                      src={`/api/niche1/media/${generatedVideo.filename}`}
                      style={{ width: "100%", maxWidth: 400, borderRadius: 8 }}
                    />
                    <Stack direction="row" spacing={1.5}>
                      <Button
                        variant="contained"
                        onClick={() => setActiveStep(4)}
                        startIcon={<CheckCircleIcon />}
                        sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                      >
                        Add Captions & Music
                      </Button>
                      <Button
                        variant="outlined"
                        onClick={handleFinalize}
                        sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                      >
                        Skip (raw video)
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Stack>
            )}

            {/* Step 4: Finalize */}
            {activeStep === 4 && (
              <Stack spacing={2}>
                <Typography variant="h6" sx={{ fontWeight: 700 }}>5. Finalize</Typography>
                <Typography variant="body2" sx={{ color: "text.secondary" }}>
                  Add animated captions and background music.
                </Typography>
                {!finalVideo ? (
                  <Stack direction="row" spacing={2} alignItems="center">
                    <Button
                      variant="contained"
                      onClick={handleFinalize}
                      disabled={loading}
                      startIcon={loading ? <CircularProgress size={18} /> : <CheckCircleIcon />}
                      sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                    >
                      {loading ? "Processing..." : "Add Captions & Music"}
                    </Button>
                  </Stack>
                ) : null}
                {finalVideo && (
                  <Stack spacing={2}>
                    <Chip icon={<CheckCircleIcon />} label="Final video ready!" color="success" />
                    <video
                      controls
                      src={finalVideo.url}
                      style={{ width: "100%", maxWidth: 400, borderRadius: 8 }}
                    />
                    <Stack direction="row" spacing={1.5}>
                      <Button
                        variant="contained"
                        onClick={() => {
                          setGeneratedImage(null)
                          setGeneratedScript(null)
                          setGeneratedAudio(null)
                          setGeneratedVideo(null)
                          setFinalVideo(null)
                          setActiveStep(0)
                        }}
                        sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                      >
                        Create Another
                      </Button>
                    </Stack>
                  </Stack>
                )}
              </Stack>
            )}

            {/* Step 5: Done (all steps complete) */}
            {activeStep >= 5 && (
              <Stack spacing={2} alignItems="center" sx={{ py: 4 }}>
                <CheckCircleIcon sx={{ fontSize: 64, color: "success.main" }} />
                <Typography variant="h5" sx={{ fontWeight: 700 }}>All done!</Typography>
                {finalVideo && (
                  <video
                    controls
                    src={finalVideo.url}
                    style={{ width: "100%", maxWidth: 400, borderRadius: 8 }}
                  />
                )}
                <Button
                  variant="contained"
                  onClick={() => {
                    setGeneratedImage(null)
                    setGeneratedScript(null)
                    setGeneratedAudio(null)
                    setGeneratedVideo(null)
                    setFinalVideo(null)
                    setActiveStep(0)
                  }}
                  sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
                >
                  Create Another
                </Button>
              </Stack>
            )}
          </Paper>
        </Stack>

        {/* History */}
        {history && history.videos?.length > 0 && (
          <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
            <Typography variant="h6" sx={{ fontWeight: 700, mb: 2 }}>
              Past Generations ({history.videos.length})
            </Typography>
            <Stack spacing={1}>
              {history.videos.slice().reverse().slice(0, 10).map((v) => (
                <Stack key={v.id} direction="row" spacing={2} alignItems="center">
                  <VideocamIcon sx={{ color: "primary.main", fontSize: 20 }} />
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    {v.video} — {new Date(v.created_at).toLocaleDateString()}
                  </Typography>
                  <Tooltip title="Play">
                    <IconButton size="small" onClick={() => window.open(`/api/niche1/media/${v.video}`, "_blank")}>
                      <PlayArrowIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Stack>
              ))}
            </Stack>
          </Paper>
        )}
      </Stack>
    </Box>
  )
}
