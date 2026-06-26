import { useCallback, useEffect, useState } from "react"
import {
  Box, Typography, Button, Stack, Paper, TextField, CircularProgress, Chip, MenuItem,
} from "@mui/material"
import MovieFilterIcon from "@mui/icons-material/MovieFilter"
import AudioUpload from "../components/create/AudioUpload"
import AssetDropzone from "../components/longform/AssetDropzone"
import SceneCard from "../components/longform/SceneCard"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"
import useAppStore from "../store/appStore"
import http from "../api/http"
import { ws } from "../api/websocket"

export default function LongFormVideo() {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const startJob = useAppStore((s) => s.startJob)

  const [step, setStep] = useState("upload") // upload | board
  const [topic, setTopic] = useState("")
  const [masterAudio, setMasterAudio] = useState(null)
  const [assets, setAssets] = useState([])
  const [aspectRatio, setAspectRatio] = useState("9:16")
  const [projectId, setProjectId] = useState(null)
  const [storyboard, setStoryboard] = useState(null)
  const [projectAssets, setProjectAssets] = useState([])
  const [planning, setPlanning] = useState(false)
  const [generatingAll, setGeneratingAll] = useState(false)
  const [generatingScene, setGeneratingScene] = useState(null)
  const [assembling, setAssembling] = useState(false)

  const fetchStoryboard = useCallback(async (pid) => {
    const { data } = await http.get(`/api/longform/projects/${pid}/storyboard`)
    setStoryboard(data.storyboard)
    setProjectAssets(data.assets || [])
    return data
  }, [])

  useEffect(() => {
    const unsubs = [
      ws.on("job_complete", (msg) => {
        if (msg.result?.storyboard && msg.result?.project_id) {
          setStoryboard(msg.result.storyboard)
          setProjectId(msg.result.project_id)
          setStep("board")
          setPlanning(false)
          showSnackbar("Storyboard ready", "success")
        } else if (msg.result?.project_id) {
          const pid = msg.result.project_id
          fetchStoryboard(pid).then(() => {
            setProjectId(pid)
            setStep("board")
            setPlanning(false)
          })
        }
      }),
      ws.on("longform_scene_start", (msg) => {
        if (msg.project_id !== projectId) return
        setGeneratingScene(msg.scene_id)
      }),
      ws.on("longform_scene_done", (msg) => {
        if (msg.project_id !== projectId) return
        setGeneratingScene(null)
        fetchStoryboard(projectId)
      }),
      ws.on("longform_generate_all_done", (msg) => {
        if (msg.project_id !== projectId) return
        setGeneratingAll(false)
        setGeneratingScene(null)
        fetchStoryboard(projectId)
        showSnackbar(`Generated ${msg.succeeded} scenes (${msg.failed} failed)`, msg.failed ? "warning" : "success")
      }),
    ]
    return () => unsubs.forEach((fn) => fn())
  }, [projectId, fetchStoryboard, showSnackbar])

  const handleSubmit = async () => {
    if (!topic.trim() || !masterAudio) {
      showSnackbar("Topic and master audio are required", "warning")
      return
    }
    setPlanning(true)
    try {
      const { data: created } = await http.post("/api/longform/projects", {
        topic: topic.trim(),
        master_audio_url: masterAudio,
        assets: assets.map((a) => ({ url: a.url, kind: a.kind, caption: a.caption || null })),
        aspect_ratio: aspectRatio,
      })
      setProjectId(created.project_id)
      const { data: planJob } = await http.post(`/api/longform/projects/${created.project_id}/plan`)
      startJob(planJob.job_id, "longform_plan", "Analyzing assets & building storyboard…")
    } catch (err) {
      setPlanning(false)
      showSnackbar(err.response?.data?.detail || "Failed to start planning", "error")
    }
  }

  const handleGenerateAll = async () => {
    if (!projectId) return
    setGeneratingAll(true)
    try {
      const { data } = await http.post(`/api/longform/projects/${projectId}/generate-all`)
      startJob(data.job_id, "longform_generate", "Generating scenes…")
    } catch (err) {
      setGeneratingAll(false)
      showSnackbar(err.response?.data?.detail || "Generate failed", "error")
    }
  }

  const handleGenerateScene = async (sceneId) => {
    if (!projectId) return
    setGeneratingScene(sceneId)
    try {
      await http.post(`/api/longform/projects/${projectId}/scenes/${sceneId}/generate`)
    } catch (err) {
      setGeneratingScene(null)
      showSnackbar(err.response?.data?.detail || "Scene generate failed", "error")
    }
  }

  const handleAssemble = async () => {
    if (!projectId) return
    setAssembling(true)
    try {
      const { data } = await http.post(`/api/longform/projects/${projectId}/assemble`)
      startJob(data.job_id, "longform_assemble", "Assembling final video…")
      showSnackbar("Assembling final video…", "info")
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Assemble failed", "error")
    } finally {
      setAssembling(false)
    }
  }

  const scenes = storyboard?.scenes || []
  const ltxCount = scenes.filter((s) => s.type === "ltx").length
  const allRendered = scenes.length > 0 && scenes.every(
    (s) => s.render_status === "done" || s.render_status === "not_needed",
  )

  if (step === "upload" || !storyboard) {
    return (
      <Box sx={{ maxWidth: 720, mx: "auto", p: { xs: 2, md: 3 } }}>
        <Stack spacing={2}>
          <Stack direction="row" spacing={1} alignItems="center">
            <MovieFilterIcon color="primary" />
            <Typography variant="h5" sx={{ fontWeight: 700 }}>Long-Form Video</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Upload your narration audio and topic assets. We will plan a storyboard with per-section audio and visual previews.
          </Typography>

          <ActiveJobsBanner />

          <TextField
            label="Topic"
            placeholder="e.g. NEET topper story"
            value={topic}
            onChange={(e) => setTopic(e.target.value)}
            fullWidth
          />

          <TextField
            select
            label="Aspect ratio"
            value={aspectRatio}
            onChange={(e) => setAspectRatio(e.target.value)}
            sx={{ maxWidth: 200 }}
          >
            <MenuItem value="9:16">9:16 (vertical)</MenuItem>
            <MenuItem value="16:9">16:9 (landscape)</MenuItem>
          </TextField>

          <AudioUpload
            label="Master audio (4–5 min)"
            value={masterAudio}
            onChange={setMasterAudio}
            onRemove={() => setMasterAudio(null)}
          />

          <AssetDropzone assets={assets} onChange={setAssets} />

          <Button
            variant="contained"
            size="large"
            disabled={planning || !topic.trim() || !masterAudio}
            onClick={handleSubmit}
            startIcon={planning ? <CircularProgress size={18} color="inherit" /> : null}
          >
            {planning ? "Planning storyboard…" : "Submit & plan storyboard"}
          </Button>
        </Stack>
      </Box>
    )
  }

  return (
    <Box sx={{ maxWidth: 900, mx: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={2}>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
          <MovieFilterIcon color="primary" />
          <Typography variant="h5" sx={{ fontWeight: 700, flex: 1 }}>{storyboard.topic}</Typography>
          <Button size="small" onClick={() => { setStep("upload"); setStoryboard(null) }}>New project</Button>
        </Stack>

        <ActiveJobsBanner />

        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center">
            <Chip label={`${scenes.length} sections`} />
            <Chip label={`${Math.round(storyboard.total_duration_s || 0)}s total`} />
            <Chip label={`${ltxCount} LTX (GPU)`} color={ltxCount ? "warning" : "default"} />
            <Box sx={{ flex: 1 }} />
            <Button
              variant="contained"
              disabled={generatingAll || !scenes.length}
              onClick={handleGenerateAll}
            >
              {generatingAll ? "Generating…" : "Generate all"}
            </Button>
            <Button
              variant="outlined"
              disabled={!allRendered || assembling}
              onClick={handleAssemble}
            >
              Assemble final video
            </Button>
          </Stack>
          {ltxCount > 0 && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: "block" }}>
              ~{ltxCount * 8}–{ltxCount * 12} min estimated GPU time for LTX scenes
            </Typography>
          )}
        </Paper>

        <Stack spacing={2}>
          {scenes.map((scene) => (
            <SceneCard
              key={scene.id}
              scene={scene}
              assets={projectAssets}
              projectId={projectId}
              onUpdate={setStoryboard}
              onGenerate={handleGenerateScene}
              generating={generatingScene === scene.id}
            />
          ))}
        </Stack>
      </Stack>
    </Box>
  )
}
