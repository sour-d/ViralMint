import { useEffect, useState } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Box, Typography, Button, Stack, Paper, TextField, Chip, CircularProgress, Tooltip,
} from "@mui/material"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import SmartDisplayIcon from "@mui/icons-material/SmartDisplay"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import ImageUpload from "../components/create/ImageUpload"
import AudioUpload from "../components/create/AudioUpload"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"
import RunPodStatusCard from "../components/runpod/RunPodStatusCard"
import useAppStore from "../store/appStore"
import http from "../api/http"
import { creatorNiches } from "../data/creatorNiches"

const AUDIO_KIND_LABEL = {
  speech: "Speech",
  commentary: "Commentary",
  song_with_vocals: "Song + vocals",
  music: "Music",
  ambient: "Ambient",
}

const AUDIO_KIND_COLOR = {
  speech: "secondary",
  commentary: "warning",
  song_with_vocals: "primary",
  music: "info",
  ambient: "default",
}

const SUBJECT_ROLE_LABEL = {
  speaker: "subject: speaker",
  listener_reactor: "subject: reacting",
  performer: "subject: performing",
  dancer_or_mover: "subject: dancing",
}

function labelForKind(kind) {
  return (AUDIO_KIND_LABEL[kind] || "audio").toLowerCase()
}

export default function AiVideo() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const startJob = useAppStore((s) => s.startJob)

  const [prompt, setPrompt] = useState("")
  const [startImage, setStartImage] = useState(null)
  const [referenceAudio, setReferenceAudio] = useState(null)
  const [lengthSeconds, setLengthSeconds] = useState(5)
  const [canGenerate, setCanGenerate] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [autoPrompting, setAutoPrompting] = useState(false)
  const [autoMeta, setAutoMeta] = useState(null)

  useEffect(() => {
    const preset = searchParams.get("preset")
    if (!preset || prompt.trim()) return
    const niche = creatorNiches.find((item) => item.slug === preset)
    if (niche) {
      setPrompt(niche.promptSeed)
    }
  }, [prompt, searchParams])

  const handleAutoPrompt = async () => {
    if (!startImage || !referenceAudio) {
      showSnackbar("Upload the start image and reference audio first", "warning")
      return
    }
    setAutoPrompting(true)
    try {
      const { data } = await http.post(
        "/api/generate/prompt-from-media",
        {
          start_image: startImage,
          reference_audio: referenceAudio,
          length_seconds: Math.min(60, Math.max(1, Number(lengthSeconds) || 5)),
        },
        // First call can take 60–120s: Whisper-small numba JIT (one-time)
        // + transcription + free OpenRouter LLM. Override the global 30s.
        { timeout: 180000 },
      )
      setPrompt(data.prompt || "")
      setAutoMeta({
        audio_kind: data.audio_kind,
        subject_role: data.subject_role,
        genre: data.genre,
        mood: data.mood,
        energy_label: data.energy_label,
        bpm: data.audio?.bpm,
        key_guess: data.audio?.key_guess,
        brightness_label: data.audio?.brightness_label,
        has_speech: data.audio?.has_speech,
        language: data.audio?.language,
        transcript: data.audio?.transcript,
      })
      showSnackbar(`Prompt written from ${labelForKind(data.audio_kind)}`, "success")
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setAutoPrompting(false)
    }
  }

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      showSnackbar("Enter a prompt describing the video", "warning")
      return
    }
    if (!startImage) {
      showSnackbar("Upload a start image", "warning")
      return
    }
    if (!referenceAudio) {
      showSnackbar("Upload reference audio (required for this workflow)", "warning")
      return
    }
    if (!canGenerate) {
      showSnackbar("Deploy the pod, install models, and wait until ready", "warning")
      return
    }

    setGenerating(true)
    try {
      const { data } = await http.post("/api/generate/runpod", {
        prompt: prompt.trim(),
        start_image: startImage,
        reference_audio: referenceAudio,
        length_seconds: Math.min(60, Math.max(1, Number(lengthSeconds) || 5)),
      })
      startJob(data.job_id, "runpod_generate", "Generating AI video on RunPod…")
      showSnackbar("AI video generation started!", "success")
      navigate("/videos?tab=generated")
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setGenerating(false)
    }
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      <Box sx={{
        px: 3, py: 2, flexShrink: 0,
        borderBottom: 1, borderColor: "divider",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: (t) => t.palette.mode === "dark"
          ? "linear-gradient(135deg, rgba(25,118,210,0.12) 0%, rgba(30,28,26,1) 100%)"
          : "linear-gradient(135deg, rgba(25,118,210,0.08) 0%, rgba(255,255,255,1) 100%)",
      }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <SmartDisplayIcon sx={{ color: "primary.main", fontSize: 26 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: -0.3 }}>
              AI Video
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Image + audio → video via ComfyUI on RunPod (assets uploaded from this app)
            </Typography>
          </Box>
        </Stack>

        <Button
          variant="contained"
          size="medium"
          disabled={generating || !canGenerate || !prompt.trim() || !startImage || !referenceAudio}
          onClick={handleGenerate}
          startIcon={<MovieCreationIcon />}
          sx={{ borderRadius: 2, fontWeight: 600, textTransform: "none", px: 2.5 }}
        >
          {generating ? "Starting…" : "Generate Video"}
        </Button>
      </Box>

      <ActiveJobsBanner filter={(j) => j.jobType === "runpod_generate"} />

      <Box sx={{ flex: 1, overflow: "auto", p: 3, maxWidth: 720, mx: "auto", width: "100%" }}>
        <RunPodStatusCard onReadyChange={setCanGenerate} />

        <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2 }}>
          <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "text.secondary", mb: 2 }}>
            Generation inputs
          </Typography>

          <Stack spacing={2.5}>
            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                Start image
              </Typography>
              <ImageUpload
                label="Reference frame"
                value={startImage}
                onChange={setStartImage}
                onRemove={() => setStartImage(null)}
              />
            </Box>

            <Box>
              <Typography variant="body2" sx={{ fontWeight: 600, mb: 1 }}>
                Reference audio
              </Typography>
              <AudioUpload
                label="Background music / rhythm track"
                value={referenceAudio}
                onChange={setReferenceAudio}
                onRemove={() => setReferenceAudio(null)}
              />
            </Box>

            <TextField
              label="Length (seconds)"
              type="number"
              fullWidth
              value={lengthSeconds}
              onChange={(e) => {
                const raw = e.target.value
                if (raw === "") {
                  setLengthSeconds("")
                  return
                }
                const n = Number(raw)
                if (!Number.isNaN(n)) {
                  setLengthSeconds(n)
                }
              }}
              onBlur={() => {
                const n = Number(lengthSeconds)
                if (!Number.isFinite(n) || n < 1) {
                  setLengthSeconds(5)
                } else {
                  setLengthSeconds(Math.min(60, Math.max(1, Math.round(n))))
                }
              }}
              inputProps={{ min: 1, max: 60, step: 1 }}
              helperText="Used by Auto-write for timestamps and by ComfyUI for output duration (1–60s)"
            />

            <Box>
              <Stack
                direction="row"
                spacing={1}
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1 }}
              >
                <Typography variant="body2" sx={{ fontWeight: 600 }}>
                  Prompt
                </Typography>
                <Tooltip
                  title={
                    !startImage || !referenceAudio
                      ? "Upload start image and reference audio first"
                      : "Analyze image + audio and auto-write a timestamped prompt"
                  }
                >
                  <span>
                    <Button
                      size="small"
                      variant="outlined"
                      startIcon={autoPrompting
                        ? <CircularProgress size={14} thickness={5} />
                        : <AutoAwesomeIcon fontSize="small" />}
                      onClick={handleAutoPrompt}
                      disabled={autoPrompting || !startImage || !referenceAudio}
                      sx={{ textTransform: "none", borderRadius: 1.5, py: 0.25 }}
                    >
                      {autoPrompting ? "Writing…" : "Auto-write"}
                    </Button>
                  </span>
                </Tooltip>
              </Stack>

              {autoMeta && (
                <Box sx={{ mb: 1 }}>
                  <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                    {autoMeta.audio_kind && (
                      <Chip
                        size="small"
                        color={AUDIO_KIND_COLOR[autoMeta.audio_kind] || "default"}
                        label={AUDIO_KIND_LABEL[autoMeta.audio_kind] || autoMeta.audio_kind}
                      />
                    )}
                    {autoMeta.subject_role && (
                      <Chip
                        size="small"
                        color="success"
                        variant="outlined"
                        label={SUBJECT_ROLE_LABEL[autoMeta.subject_role] || autoMeta.subject_role}
                      />
                    )}
                    {["song_with_vocals", "music"].includes(autoMeta.audio_kind) && autoMeta.bpm != null && (
                      <Chip size="small" variant="outlined"
                            label={`${Math.round(autoMeta.bpm)} BPM`} />
                    )}
                    {autoMeta.language && (
                      <Chip size="small" variant="outlined"
                            label={`lang: ${autoMeta.language}`} />
                    )}
                    {autoMeta.genre && (
                      <Chip size="small" color="primary" variant="outlined"
                            label={autoMeta.genre} />
                    )}
                    {autoMeta.mood && (
                      <Chip size="small" variant="outlined" label={autoMeta.mood} />
                    )}
                    {autoMeta.energy_label && (
                      <Chip size="small" variant="outlined"
                            label={`energy: ${autoMeta.energy_label}`} />
                    )}
                    {["song_with_vocals", "music"].includes(autoMeta.audio_kind) && autoMeta.brightness_label && (
                      <Chip size="small" variant="outlined"
                            label={autoMeta.brightness_label} />
                    )}
                    {["song_with_vocals", "music"].includes(autoMeta.audio_kind) && autoMeta.key_guess && (
                      <Chip size="small" variant="outlined" label={autoMeta.key_guess} />
                    )}
                  </Stack>
                  {autoMeta.has_speech && autoMeta.transcript && (
                    <Typography
                      variant="caption"
                      sx={{
                        mt: 0.75,
                        color: "text.secondary",
                        fontStyle: "italic",
                        overflow: "hidden",
                        display: "-webkit-box",
                        WebkitBoxOrient: "vertical",
                        WebkitLineClamp: 2,
                      }}
                      title={autoMeta.transcript}
                    >
                      &ldquo;{autoMeta.transcript}&rdquo;
                    </Typography>
                  )}
                </Box>
              )}

              <TextField
                multiline
                minRows={3}
                fullWidth
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe the motion and scene for your video, or click Auto-write…"
              />
            </Box>
          </Stack>
        </Paper>
      </Box>
    </Box>
  )
}
