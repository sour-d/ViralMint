import { useState } from "react"
import { useNavigate } from "react-router-dom"
import {
  Box, Typography, Button, Stack, Paper, TextField,
} from "@mui/material"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import SmartDisplayIcon from "@mui/icons-material/SmartDisplay"
import ImageUpload from "../components/create/ImageUpload"
import AudioUpload from "../components/create/AudioUpload"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"
import RunPodStatusCard from "../components/runpod/RunPodStatusCard"
import useAppStore from "../store/appStore"
import http from "../api/http"

export default function AiVideo() {
  const navigate = useNavigate()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const startJob = useAppStore((s) => s.startJob)

  const [prompt, setPrompt] = useState("")
  const [startImage, setStartImage] = useState(null)
  const [referenceAudio, setReferenceAudio] = useState(null)
  const [lengthSeconds, setLengthSeconds] = useState(5)
  const [canGenerate, setCanGenerate] = useState(false)
  const [generating, setGenerating] = useState(false)

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
              label="Prompt"
              multiline
              minRows={3}
              fullWidth
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe the motion and scene for your video…"
            />

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
              helperText="Maps to the workflow Duration node (1–60 seconds)"
            />
          </Stack>
        </Paper>
      </Box>
    </Box>
  )
}
