import { useState, useEffect } from "react"
import { useNavigate } from "react-router-dom"
import {
  Box, Typography, Button, Stack, Paper, TextField, Chip,
  FormControl, InputLabel, Select, MenuItem, ToggleButton, ToggleButtonGroup,
  Tooltip, Divider,
} from "@mui/material"
import PhotoLibraryIcon from "@mui/icons-material/PhotoLibrary"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import ImageIcon from "@mui/icons-material/Image"
import FolderOpenIcon from "@mui/icons-material/FolderOpen"
import useAppStore from "../store/appStore"
import useSettings from "../hooks/useSettings"
import useRemoteConfig from "../hooks/useRemoteConfig"
import useScriptGeneration from "../hooks/useScriptGeneration"
import useSourceVideo from "../hooks/useSourceVideo"
import http from "../api/http"

import ScriptPanel from "../components/create/ScriptPanel"
import SceneStoryboard from "../components/create/SceneStoryboard"
import AudioConfig from "../components/create/AudioConfig"
import EstimatedCost from "../components/create/EstimatedCost"
import ImageUpload from "../components/create/ImageUpload"
import TemplateGallery from "../components/create/TemplateGallery"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"

export default function StockVideo() {
  const navigate = useNavigate()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const { settings } = useSettings()

  const { data: TTS_PROVIDERS } = useRemoteConfig("tts_providers")
  const { data: CAPTION_STYLES } = useRemoteConfig("caption_styles")
  const { data: MUSIC_GENRES } = useRemoteConfig("music_genres")

  const { source, sourceLoading, sourceId } = useSourceVideo()
  const {
    script, setScript, scriptInstructions, setScriptInstructions,
    scriptLoading, scriptGenerated, handleGenerateScript, handlePolishScript,
    splitIntoScenes,
  } = useScriptGeneration()

  // Config state
  const [aspectRatio, setAspectRatio] = useState("9:16")
  const [operation, setOperation] = useState("t2v")
  const [startImage, setStartImage] = useState(null)
  const [ttsProvider, setTtsProvider] = useState("edge_tts")
  const [captionEnabled, setCaptionEnabled] = useState(true)
  const [captionStyle, setCaptionStyle] = useState("viral")
  const [musicEnabled, setMusicEnabled] = useState(true)
  const [musicGenre, setMusicGenre] = useState("lofi")

  // Scenes
  const [scenes, setScenes] = useState([])
  const [splitLoading, setSplitLoading] = useState(false)
  const [generating, setGenerating] = useState(false)

  // Load defaults from settings
  useEffect(() => {
    if (settings) {
      setTtsProvider(settings.tts_provider || "edge_tts")
      setCaptionEnabled(settings.caption_enabled !== false)
      setCaptionStyle(settings.caption_style || "viral")
      setMusicEnabled(settings.music_enabled !== false)
      setMusicGenre(settings.music_genre || "lofi")
    }
  }, [settings])

  const handleSplitScenes = async () => {
    setSplitLoading(true)
    const result = await splitIntoScenes("stock", aspectRatio, sourceId)
    if (result) {
      setScenes(result.map(s => ({
        text: s.text || "",
        keywords: s.keywords || [],
      })))
    }
    setSplitLoading(false)
  }

  const handleGenerate = async () => {
    if (!script?.trim()) {
      showSnackbar("Please write a script or generate one with AI first", "warning")
      return
    }

    setGenerating(true)
    try {
      const body = {
        script: script.trim(),
        aspect_ratio: aspectRatio,
        tts_provider: ttsProvider,
        caption_enabled: captionEnabled,
        caption_style: captionEnabled ? captionStyle : undefined,
        music_enabled: musicEnabled,
        music_genre: musicEnabled ? musicGenre : undefined,
        source_id: sourceId || undefined,
        start_image: operation === "i2v" ? startImage : undefined,
        scenes: scenes.length > 0
          ? scenes.filter(s => s.text.trim()).map(s => ({ text: s.text, keywords: s.keywords || [] }))
          : undefined,
      }
      await http.post("/api/generate/stock", body)
      showSnackbar("Stock video generation started!", "success")
      navigate("/videos?tab=generated")
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setGenerating(false)
    }
  }

  const handleApplyTemplate = (defaults) => {
    if (defaults.captionStyle) setCaptionStyle(defaults.captionStyle)
    if (defaults.musicGenre) setMusicGenre(defaults.musicGenre)
    if (defaults.aspectRatio) setAspectRatio(defaults.aspectRatio)
    if (defaults.scriptInstructions) setScriptInstructions(defaults.scriptInstructions)
  }

  const audioProps = {
    ttsProvider, setTtsProvider, captionEnabled, setCaptionEnabled,
    captionStyle, setCaptionStyle, musicEnabled, setMusicEnabled, musicGenre, setMusicGenre,
    TTS_PROVIDERS, CAPTION_STYLES, MUSIC_GENRES, script,
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* ── Header ────────────────────────────────────────── */}
      <Box sx={{
        px: 3, py: 2, flexShrink: 0,
        borderBottom: 1, borderColor: "divider",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: (t) => t.palette.mode === "dark"
          ? "linear-gradient(135deg, rgba(56,142,60,0.10) 0%, rgba(30,28,26,1) 100%)"
          : "linear-gradient(135deg, rgba(56,142,60,0.07) 0%, rgba(255,255,255,1) 100%)",
      }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <PhotoLibraryIcon sx={{ color: "success.main", fontSize: 26 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: -0.3 }}>
              Stock Video
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Free videos with Pexels stock footage matched to your script
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Open generated folder">
            <Button size="small" variant="outlined" sx={{ minWidth: 0, px: 1 }}
              onClick={() => http.post("/api/settings/open-folder", { folder: "generated" }).catch(() => showSnackbar("Could not open folder", "error"))}>
              <FolderOpenIcon fontSize="small" />
            </Button>
          </Tooltip>
          <Button
            variant="contained" size="medium"
            disabled={generating || !script?.trim()}
            onClick={handleGenerate}
            startIcon={<MovieCreationIcon />}
            sx={{ borderRadius: 2, fontWeight: 600, textTransform: "none", px: 2.5 }}
          >
            {generating ? "Starting..." : "Generate Video"}
          </Button>
        </Stack>
      </Box>

      {/* ── Active Jobs Progress ─────────────────────────── */}
      <ActiveJobsBanner />

      {/* ── Templates (collapsible strip) ────────────────── */}
      <Box sx={{ px: 3, pt: 2, pb: 0.5, flexShrink: 0 }}>
        <TemplateGallery mode="stock" onApply={handleApplyTemplate} />
      </Box>

      {/* ── 3-Panel Layout ───────────────────────────────── */}
      <Box sx={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* Left Panel: Script */}
        <Box sx={{
          flex: 5, overflow: "auto", p: 2.5,
          borderRight: 1, borderColor: "divider",
        }}>
          <ScriptPanel
            source={source}
            script={script} setScript={setScript}
            scriptInstructions={scriptInstructions} setScriptInstructions={setScriptInstructions}
            onGenerateScript={() => handleGenerateScript(sourceId, aspectRatio)}
            onPolishScript={handlePolishScript}
            scriptLoading={scriptLoading}
            scriptGenerated={scriptGenerated}
            sourceId={sourceId}
            mode="stock"
          >
            {operation === "i2v" && (
              <Paper variant="outlined" sx={{ p: 2, borderRadius: 2 }}>
                <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "text.secondary", mb: 1 }}>
                  <ImageIcon sx={{ fontSize: 16, verticalAlign: "text-bottom", mr: 0.5 }} />
                  Input Image
                </Typography>
                <ImageUpload label="Image" value={startImage} onChange={setStartImage} onRemove={() => setStartImage(null)} />
              </Paper>
            )}
          </ScriptPanel>
        </Box>

        {/* Center Panel: Scene Storyboard */}
        <Box sx={{ flex: 4, overflow: "auto", p: 2.5, borderRight: 1, borderColor: "divider" }}>
          <SceneStoryboard
            scenes={scenes}
            setScenes={setScenes}
            onSplitScript={handleSplitScenes}
            splitLoading={splitLoading}
            maxScenes={12}
            showSplitButton={!!script?.trim()}
            emptyMessage="Write a script first, then click 'Split into Scenes' to generate keyword-tagged scenes for stock footage matching."
            renderCard={(scene, idx, updateScene) => (
              <StockSceneCard scene={scene} idx={idx} updateScene={updateScene} />
            )}
          />
        </Box>

        {/* Right Panel: Configuration */}
        <Box sx={{ flex: 3, overflow: "auto", p: 2.5, minWidth: 240 }}>
          <Typography variant="overline" sx={{ color: "text.secondary", fontWeight: 700, fontSize: "0.65rem", mb: 1.5, display: "block" }}>
            Configuration
          </Typography>

          <Stack spacing={1.5}>
            {/* Operation toggle */}
            <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>Mode</Typography>
            <ToggleButtonGroup value={operation} exclusive onChange={(_, v) => v && setOperation(v)} size="small" fullWidth
              sx={{ "& .MuiToggleButton-root": { textTransform: "none", fontSize: "0.8rem", py: 0.5 } }}>
              <ToggleButton value="t2v">Script to Video</ToggleButton>
              <ToggleButton value="i2v"><ImageIcon sx={{ fontSize: 16, mr: 0.5 }} />Image to Video</ToggleButton>
            </ToggleButtonGroup>

            <Divider />

            <FormControl fullWidth size="small">
              <InputLabel>Aspect Ratio</InputLabel>
              <Select value={aspectRatio} onChange={e => setAspectRatio(e.target.value)} label="Aspect Ratio">
                <MenuItem value="9:16">9:16 — Vertical (TikTok, Shorts)</MenuItem>
                <MenuItem value="16:9">16:9 — Horizontal (YouTube)</MenuItem>
              </Select>
            </FormControl>

            <Divider />
            <AudioConfig {...audioProps} />
            <Divider />
            <EstimatedCost mode="stock" model={null} ttsProvider={ttsProvider} script={script} />
          </Stack>
        </Box>
      </Box>
    </Box>
  )
}

/* ── Stock Scene Card ────────────────────────────────────────────── */

function StockSceneCard({ scene, idx, updateScene }) {
  const [editingKeyword, setEditingKeyword] = useState("")

  const handleAddKeyword = () => {
    const kw = editingKeyword.trim()
    if (kw && !(scene.keywords || []).includes(kw)) {
      updateScene({ keywords: [...(scene.keywords || []), kw] })
    }
    setEditingKeyword("")
  }

  const handleRemoveKeyword = (kw) => {
    updateScene({ keywords: (scene.keywords || []).filter(k => k !== kw) })
  }

  const wordCount = scene.text ? scene.text.trim().split(/\s+/).filter(Boolean).length : 0
  const estSec = wordCount > 0 ? Math.ceil(wordCount / 2.5) : 0

  return (
    <>
      <TextField
        multiline rows={3} fullWidth size="small"
        value={scene.text}
        onChange={e => updateScene({ text: e.target.value })}
        placeholder={`Scene ${idx + 1} narration...`}
        sx={{ mb: 1, "& .MuiOutlinedInput-root": { fontSize: "0.82rem" } }}
      />
      <Box sx={{ mb: 0.75 }}>
        <Typography variant="caption" sx={{ color: "text.secondary", fontWeight: 600, mb: 0.5, display: "block" }}>
          Pexels Keywords
        </Typography>
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap sx={{ gap: 0.5 }}>
          {(scene.keywords || []).map(kw => (
            <Chip key={kw} label={kw} size="small" variant="outlined"
              onDelete={() => handleRemoveKeyword(kw)}
              sx={{ fontSize: "0.72rem", height: 24 }} />
          ))}
          <TextField
            size="small" variant="standard"
            placeholder="+ keyword"
            value={editingKeyword}
            onChange={e => setEditingKeyword(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); handleAddKeyword() } }}
            onBlur={handleAddKeyword}
            sx={{ width: 80, "& .MuiInput-input": { fontSize: "0.75rem", py: 0.25 } }}
          />
        </Stack>
      </Box>
      {wordCount > 0 && (
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          ~{estSec}s ({wordCount} words)
        </Typography>
      )}
    </>
  )
}
