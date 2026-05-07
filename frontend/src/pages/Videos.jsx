import { useState, useEffect, useCallback, Fragment } from "react"
import { useNavigate, useSearchParams } from "react-router-dom"
import {
  Box, Typography, Tabs, Tab, Button, Chip, Stack, Paper, IconButton,
  Collapse, TablePagination,
  CircularProgress, Tooltip,
} from "@mui/material"
import FileUploadIcon from "@mui/icons-material/FileUpload"
import FolderOpenIcon from "@mui/icons-material/FolderOpen"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import ExpandMoreIcon from "@mui/icons-material/ExpandMore"
import ExpandLessIcon from "@mui/icons-material/ExpandLess"
import RefreshIcon from "@mui/icons-material/Refresh"
import WorkIcon from "@mui/icons-material/WorkOutline"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import TravelExploreIcon from "@mui/icons-material/TravelExplore"
import CloudDownloadIcon from "@mui/icons-material/CloudDownload"
import VideoLibraryIcon from "@mui/icons-material/VideoLibrary"
import AudiotrackIcon from "@mui/icons-material/Audiotrack"
import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline"
import PhotoLibraryIcon from "@mui/icons-material/PhotoLibrary"
import WhatshotIcon from "@mui/icons-material/Whatshot"
import NewspaperIcon from "@mui/icons-material/Newspaper"
import WarningAmberIcon from "@mui/icons-material/WarningAmber"
import Dialog from "@mui/material/Dialog"
import DialogTitle from "@mui/material/DialogTitle"
import DialogContent from "@mui/material/DialogContent"
import DialogActions from "@mui/material/DialogActions"
import http from "../api/http"
import useAppStore from "../store/appStore"
import useJobs from "../hooks/useJobs"
import ActiveJobsBanner from "../components/create/ActiveJobsBanner"
import { STATUS_COLOR } from "../components/videos/constants"
import CreateModeMenu from "../components/videos/CreateModeMenu"
import ScoutTab from "../components/videos/ScoutTab"
import JobHistoryTab from "../components/videos/JobHistoryTab"
import DownloadedDetail from "../components/videos/DownloadedDetail"
import GeneratedDetail from "../components/videos/GeneratedDetail"

/* ── Main page ──────────────────────────────────────────────────── */

export default function Videos() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const removeJob = useAppStore((s) => s.removeJob)
  const { jobs, jobTotal, fetchJobs } = useJobs(5000)

  // Tab: 0=Scout Results, 1=Downloaded, 2=Generated, 3=Job History
  const tabMap = { scout: 0, downloaded: 1, generated: 2, jobs: 3 }
  const initialTab = tabMap[searchParams.get("tab")] ?? 1
  const [tab, setTab] = useState(initialTab)

  const [scoutResults, setScoutResults] = useState([])
  const [scoutTotal, setScoutTotal] = useState(0)
  const [scoutPage, setScoutPage] = useState(0)
  const [scoutRowsPerPage, setScoutRowsPerPage] = useState(50)

  const [downloadedVideos, setDownloadedVideos] = useState([])
  const [dlTotal, setDlTotal] = useState(0)
  const [dlPage, setDlPage] = useState(0)
  const [dlRowsPerPage, setDlRowsPerPage] = useState(20)

  const [generatedVideos, setGeneratedVideos] = useState([])
  const [genTotal, setGenTotal] = useState(0)
  const [genPage, setGenPage] = useState(0)
  const [genRowsPerPage, setGenRowsPerPage] = useState(20)

  const [jobPage, setJobPage] = useState(0)
  const [jobRowsPerPage, setJobRowsPerPage] = useState(20)

  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState("")
  const [expandedId, setExpandedId] = useState(null)
  const [detailVideo, setDetailVideo] = useState(null)

  // Create mode picker menu state
  const [createMenuAnchor, setCreateMenuAnchor] = useState(null)
  const [createMenuSourceId, setCreateMenuSourceId] = useState(null)
  const openCreateMenu = (e, sourceId) => { e.stopPropagation(); setCreateMenuAnchor(e.currentTarget); setCreateMenuSourceId(sourceId) }

  const fetchResults = useCallback(async (jobId = null, offset = 0, limit = 50) => {
    try {
      const params = new URLSearchParams({ limit, offset })
      if (jobId) params.set("job_id", jobId)
      const { data } = await http.get(`/api/scout/results?${params}`)
      setScoutResults(data.results || [])
      setScoutTotal(data.total || 0)
    } catch (err) { showSnackbar("Failed to load scout results", "error") }
  }, [])

  const fetchDownloaded = useCallback(async (offset = 0, limit = 20) => {
    try {
      const res = await http.get("/api/downloaded", { params: { limit, offset } })
      setDownloadedVideos(res.data.videos || [])
      setDlTotal(res.data.total || 0)
    } catch (e) { showSnackbar("Failed to load downloaded videos", "error") }
  }, [])

  const fetchGenerated = useCallback(async (offset = 0, limit = 20) => {
    try {
      const params = { limit, offset }
      if (filter) params.status = filter
      const res = await http.get("/api/videos", { params })
      setGeneratedVideos(res.data.videos || [])
      setGenTotal(res.data.total || 0)
    } catch (e) { showSnackbar("Failed to load generated videos", "error") }
  }, [filter])

  useEffect(() => {
    setLoading(true)
    Promise.all([
      fetchResults(null, 0, scoutRowsPerPage),
      fetchDownloaded(0, dlRowsPerPage),
      fetchGenerated(0, genRowsPerPage),
      fetchJobs(),
    ]).finally(() => setLoading(false))
  }, [])

  useEffect(() => { fetchGenerated(genPage * genRowsPerPage, genRowsPerPage) }, [fetchGenerated])

  useEffect(() => {
    const downloadJobs = jobs.filter(j => j.job_type === "download" && j.status === "success")
    if (downloadJobs.length > 0) fetchDownloaded(dlPage * dlRowsPerPage, dlRowsPerPage)
  }, [jobs])

  const refreshAll = async () => {
    try { await http.post("/api/downloaded/cleanup") } catch (_) {}
    fetchResults(null, 0, scoutRowsPerPage)
    fetchDownloaded(0, dlRowsPerPage)
    fetchGenerated(0, genRowsPerPage)
    fetchJobs()
    setScoutPage(0); setDlPage(0); setGenPage(0); setJobPage(0)
  }

  const toggleExpand = (id, fetcher) => {
    if (expandedId === id) {
      setExpandedId(null)
      setDetailVideo(null)
    } else {
      setExpandedId(id)
      if (fetcher) fetcher()
    }
  }

  const handleDeleteVideo = async (id) => {
    try {
      await http.delete(`/api/videos/${id}`)
      setGeneratedVideos(prev => prev.filter(v => v.id !== id))
      if (expandedId === id) { setExpandedId(null); setDetailVideo(null) }
    } catch (e) { showSnackbar(e.response?.data?.detail || "Failed to delete video", "error") }
  }

  const handleDeleteDownloaded = async (id) => {
    try {
      await http.delete(`/api/downloaded/${id}`)
      setDownloadedVideos(prev => prev.filter(v => v.id !== id))
      setDlTotal(prev => prev - 1)
      if (expandedId === id) { setExpandedId(null); setDetailVideo(null) }
      showSnackbar("Video deleted", "success")
    } catch (e) {
      showSnackbar(e.response?.data?.detail || "Delete failed", "error")
    }
  }

  const handleUpload = async (id, platforms) => {
    try {
      await http.post(`/api/videos/${id}/upload`, { platforms })
      showSnackbar(`Upload started for ${platforms.join(", ")}`, "success")
      fetchGenerated()
    } catch (e) { showSnackbar(e.response?.data?.detail || e.message, "error") }
  }

  const handleCancelJob = async (jobId) => {
    try {
      await http.delete(`/api/jobs/${jobId}`)
      removeJob(jobId)
      showSnackbar("Job cancelled", "info")
      fetchJobs()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Failed to cancel job", "error")
    }
  }

  const handleDeleteJob = async (jobId) => {
    try {
      await http.delete(`/api/jobs/${jobId}`)
      showSnackbar("Job deleted", "info")
      fetchJobs()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Failed to delete job", "error")
    }
  }

  const handleBulkDeleteJobs = (jobIds, onDone) => {
    openConfirm(
      "Delete jobs",
      `Delete ${jobIds.length} job${jobIds.length > 1 ? "s" : ""}? This cannot be undone.`,
      async () => {
        try {
          await http.post("/api/jobs/bulk-delete", { job_ids: jobIds })
          showSnackbar(`Deleted ${jobIds.length} jobs`, "info")
          onDone?.()
          fetchJobs()
        } catch (err) {
          showSnackbar(err.response?.data?.detail || "Failed to delete jobs", "error")
        }
      }
    )
  }

  const [importing, setImporting] = useState(false)
  const [confirmDialog, setConfirmDialog] = useState({ open: false, title: "", message: "", onConfirm: null })
  const openConfirm = (title, message, onConfirm) => setConfirmDialog({ open: true, title, message, onConfirm })
  const closeConfirm = () => setConfirmDialog(prev => ({ ...prev, open: false }))
  const [uploadPreview, setUploadPreview] = useState({ open: false, videoId: null, platforms: [], video: null })
  const openUploadPreview = (id, platforms) => {
    const video = generatedVideos.find(v => v.id === id) || detailVideo
    setUploadPreview({ open: true, videoId: id, platforms, video })
  }

  const handleImportVideo = async (event) => {
    const file = event.target.files?.[0]
    if (!file) return
    event.target.value = ""
    setImporting(true)
    try {
      const formData = new FormData()
      formData.append("file", file)
      formData.append("title", file.name.replace(/\.[^.]+$/, ""))
      const res = await http.post("/api/downloaded/import", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      showSnackbar(res.data.message || "Video imported!", "success")
      await fetchDownloaded()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || "Import failed", "error")
    } finally {
      setImporting(false)
    }
  }

  const openFolder = async (folder) => {
    try { await http.post("/api/settings/open-folder", { folder }) } catch { showSnackbar("Could not open folder", "error") }
  }

  return (
    <Box sx={{ height: "100%", display: "flex", flexDirection: "column", overflow: "hidden" }}>
      {/* ── Header ────────────────────────────────────────── */}
      <Box sx={{
        px: 3, py: 2, flexShrink: 0,
        borderBottom: 1, borderColor: "divider",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        background: (t) => t.palette.mode === "dark"
          ? "linear-gradient(135deg, rgba(0,151,167,0.10) 0%, rgba(30,28,26,1) 100%)"
          : "linear-gradient(135deg, rgba(0,151,167,0.07) 0%, rgba(255,255,255,1) 100%)",
      }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <VideoLibraryIcon sx={{ color: "info.main", fontSize: 26 }} />
          <Box>
            <Typography variant="h5" sx={{ fontWeight: 700, letterSpacing: -0.3 }}>
              Library
            </Typography>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              Scout, download, analyze, and manage your video content
            </Typography>
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center">
          <Tooltip title="Refresh all data">
            <Button size="small" variant="outlined" sx={{ minWidth: 0, px: 1 }}
              onClick={refreshAll}>
              <RefreshIcon fontSize="small" />
            </Button>
          </Tooltip>
          {tab === 1 && (
            <>
              <Tooltip title="Open videos folder">
                <Button size="small" variant="outlined" sx={{ minWidth: 0, px: 1 }}
                  onClick={() => openFolder("videos")}>
                  <FolderOpenIcon fontSize="small" />
                </Button>
              </Tooltip>
              <Button size="small" variant="contained" color="secondary"
                startIcon={<FileUploadIcon />} disabled={importing} component="label">
                {importing ? "Importing..." : "Import"}
                <input type="file" hidden
                  accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.m4a,.aac,.flac"
                  onChange={handleImportVideo} />
              </Button>
            </>
          )}
          {tab === 2 && (
            <Tooltip title="Open generated folder">
              <Button size="small" variant="outlined" sx={{ minWidth: 0, px: 1 }}
                onClick={() => openFolder("generated")}>
                <FolderOpenIcon fontSize="small" />
              </Button>
            </Tooltip>
          )}
        </Stack>
      </Box>

      {/* ── Active Jobs Progress ─────────────────────────── */}
      <ActiveJobsBanner filter={(j) => j.status === "running"} onCancel={handleCancelJob} />

      {/* ── Tabs bar (sticky, non-scrolling) ─────────────── */}
      <Box sx={{ px: 3, flexShrink: 0, borderBottom: 1, borderColor: "divider" }}>
        <Tabs value={tab} onChange={(_, v) => { setTab(v); setExpandedId(null); setDetailVideo(null); if (v === 2) fetchGenerated(0, genRowsPerPage) }}
          sx={{ "& .MuiTab-root": { textTransform: "none", fontWeight: 600, minHeight: 44, fontSize: "0.85rem" } }}>
          <Tab icon={<TravelExploreIcon sx={{ fontSize: 18 }} />} iconPosition="start" label={`Scout (${scoutTotal})`} />
          <Tab icon={<CloudDownloadIcon sx={{ fontSize: 18 }} />} iconPosition="start" label={`Downloaded (${dlTotal})`} />
          <Tab icon={<VideoLibraryIcon sx={{ fontSize: 18 }} />} iconPosition="start" label={`Generated (${genTotal})`} />
          <Tab icon={<WorkIcon sx={{ fontSize: 18 }} />} iconPosition="start" label={`Jobs (${jobTotal})`} />
        </Tabs>
      </Box>

      {/* ── Scrollable content area ──────────────────────── */}
      <Box sx={{ flex: 1, overflow: "auto", p: 2.5 }}>
        {loading ? (
          <Box sx={{ py: 8, display: "flex", justifyContent: "center" }}>
            <CircularProgress size={36} />
          </Box>
        ) : (
          <>
            {/* ──── Tab 0: Scout Results ──── */}
            {tab === 0 && <ScoutTab jobs={jobs} scoutResults={scoutResults} scoutTotal={scoutTotal}
              page={scoutPage} rowsPerPage={scoutRowsPerPage}
              onFetchResults={(jobId, offset, limit) => { if (offset === 0) setScoutPage(0); fetchResults(jobId, offset, limit) }}
              onPageChange={(_, p) => { setScoutPage(p); fetchResults(null, p * scoutRowsPerPage, scoutRowsPerPage) }}
              onRowsPerPageChange={(e) => { const rpp = parseInt(e.target.value, 10); setScoutRowsPerPage(rpp); setScoutPage(0); fetchResults(null, 0, rpp) }}
            />}

            {/* ──── Tab 1: Downloaded ──── */}
            {tab === 1 && (
              downloadedVideos.length === 0 ? (
                <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
                  <CloudDownloadIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1.5 }} />
                  <Typography variant="h6" sx={{ mb: 0.5 }}>No downloaded videos yet</Typography>
                  <Typography variant="body2" sx={{ mb: 0.5 }}>
                    Import your own videos for AI analysis, or download trending videos from Scout Results.
                  </Typography>
                  <Typography variant="caption" sx={{ display: "block", mb: 2.5, color: "text.disabled" }}>
                    Supported: MP4, MOV, AVI, MKV, WebM, MP3, WAV, M4A, AAC, FLAC
                  </Typography>
                  <Stack direction="row" spacing={1.5} justifyContent="center">
                    <Button variant="contained" color="secondary" startIcon={<FileUploadIcon />}
                      disabled={importing} component="label">
                      {importing ? "Importing..." : "Import a Video or Audio"}
                      <input type="file" hidden
                        accept="video/*,audio/*,.mp4,.mov,.avi,.mkv,.webm,.mp3,.wav,.m4a,.aac,.flac"
                        onChange={handleImportVideo} />
                    </Button>
                    <Button variant="outlined" onClick={() => setTab(0)}>
                      Browse Scout Results
                    </Button>
                  </Stack>
                </Box>
              ) : (
                <>
                <Stack spacing={0}>
                  {downloadedVideos.map(v => {
                    const isExpanded = expandedId === v.id
                    return (
                      <Fragment key={v.id}>
                        <Paper
                          elevation={0}
                          onClick={() => toggleExpand(v.id, () => setDetailVideo({ ...v, _type: "downloaded" }))}
                          sx={{
                            px: 2, py: 1.25, mb: isExpanded ? 0 : 0.75,
                            border: 1,
                            borderColor: isExpanded ? "secondary.main" : "divider",
                            borderRadius: isExpanded ? "12px 12px 0 0" : 3,
                            cursor: "pointer",
                            display: "flex", alignItems: "center", gap: 1.5,
                            transition: "all 0.15s ease",
                            "&:hover": { borderColor: "secondary.light", bgcolor: "action.hover" },
                          }}
                        >
                          {/* Thumbnail */}
                          <Box sx={{
                            width: 72, height: 48, borderRadius: 1.5, overflow: "hidden",
                            bgcolor: "action.hover", flexShrink: 0,
                            display: "flex", alignItems: "center", justifyContent: "center",
                          }}>
                            {v.thumbnail_url ? (
                              <Box component="img" src={v.thumbnail_url} alt=""
                                sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
                            ) : v.platform === "news" ? (
                              <NewspaperIcon sx={{ color: "primary.main", fontSize: 22 }} />
                            ) : v.video_path ? (
                              <PlayCircleOutlineIcon sx={{ color: "text.disabled", fontSize: 22 }} />
                            ) : (
                              <AudiotrackIcon sx={{ color: "text.disabled", fontSize: 20 }} />
                            )}
                          </Box>

                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography variant="body1" sx={{ fontWeight: 500, fontSize: "0.92rem" }} noWrap>
                              {v.title || "Untitled"}
                            </Typography>
                            <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mt: 0.25 }}>
                              {v.platform && (
                                <Chip label={v.platform} size="small" variant="outlined"
                                  icon={v.platform === "news" ? <NewspaperIcon sx={{ fontSize: "12px !important" }} /> : undefined}
                                  sx={{ height: 18, fontSize: "0.6rem", textTransform: "uppercase",
                                    ...(v.platform === "news" && { borderColor: "warning.main", color: "warning.main" }) }} />
                              )}
                              {v.platform !== "news" && v.duration_seconds != null && (
                                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                                  {Math.floor(v.duration_seconds / 60)}m{v.duration_seconds % 60}s
                                </Typography>
                              )}
                              {v.platform !== "news" && v.file_size_mb && (
                                <Typography variant="caption" sx={{ color: "text.secondary" }}>{v.file_size_mb}MB</Typography>
                              )}
                              {v.platform === "news" && v.source_url && (
                                <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.7rem" }}>
                                  {(() => { try { return new URL(v.source_url).hostname.replace("www.", "") } catch { return "" } })()}
                                </Typography>
                              )}
                              <Chip
                                label={v.platform === "news"
                                  ? (v.insights ? "Analyzed" : "Saved")
                                  : (v.insights ? "Analyzed" : v.transcript ? "Transcribed" : "Downloaded")}
                                size="small"
                                color={v.insights ? "success" : v.transcript ? "warning" : "default"}
                                sx={{ height: 20, fontSize: "0.65rem" }}
                              />
                              {v.created_at && (
                                <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.7rem" }}>
                                  {new Date(v.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}
                                </Typography>
                              )}
                            </Stack>
                          </Box>
                          <Button size="small" variant="contained" startIcon={<MovieCreationIcon />}
                            onClick={(e) => openCreateMenu(e, v.id)}
                            sx={{ flexShrink: 0 }}>
                            Create
                          </Button>
                          <IconButton size="small" onClick={(e) => { e.stopPropagation(); openConfirm(v.platform === "news" ? "Delete article?" : "Delete video?", v.platform === "news" ? "This will permanently remove the saved article and its analysis." : "This will permanently remove the downloaded video and its analysis.", () => handleDeleteDownloaded(v.id)) }}
                            title={v.platform === "news" ? "Delete article" : "Delete video"} sx={{ color: "text.disabled", "&:hover": { color: "error.main" } }}>
                            <DeleteOutlineIcon sx={{ fontSize: 18 }} />
                          </IconButton>
                          <IconButton size="small" sx={{ color: "text.secondary" }}>
                            {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                          </IconButton>
                        </Paper>

                        <Collapse in={isExpanded} unmountOnExit>
                          {detailVideo?._type === "downloaded" && detailVideo.id === v.id && (
                            <DownloadedDetail
                              video={detailVideo}
                              onUseAsInspiration={(id, event) => { if (event) openCreateMenu(event, id) }}
                              onClose={() => { setExpandedId(null); setDetailVideo(null) }}
                              onDetailUpdate={(updated) => {
                                setDetailVideo(updated)
                                setDownloadedVideos(prev => prev.map(dv =>
                                  dv.id === updated.id ? { ...dv, transcript: updated.transcript?.slice(0, 200), insights: updated.insights } : dv
                                ))
                              }}
                            />
                          )}
                        </Collapse>
                      </Fragment>
                    )
                  })}
                </Stack>
                <TablePagination
                  component="div"
                  count={dlTotal}
                  page={dlPage}
                  onPageChange={(_, p) => { setDlPage(p); fetchDownloaded(p * dlRowsPerPage, dlRowsPerPage) }}
                  rowsPerPage={dlRowsPerPage}
                  onRowsPerPageChange={(e) => { const rpp = parseInt(e.target.value, 10); setDlRowsPerPage(rpp); setDlPage(0); fetchDownloaded(0, rpp) }}
                  rowsPerPageOptions={[10, 20, 50]}
                  sx={{ borderTop: 1, borderColor: "divider", mt: 1 }}
                />
                </>
              )
            )}

            {/* ──── Tab 2: Generated ──── */}
            {tab === 2 && (
              <>
                <Stack direction="row" spacing={0.5} sx={{ mb: 2 }}>
                  {["", "ready", "uploaded", "draft", "failed"].map(s => (
                    <Chip key={s} label={s || "All"} onClick={() => { setFilter(s); setExpandedId(null); setDetailVideo(null) }}
                      color={filter === s ? "secondary" : "default"} variant={filter === s ? "filled" : "outlined"} size="small" />
                  ))}
                </Stack>

                {generatedVideos.length === 0 ? (
                  <Box sx={{ textAlign: "center", py: 8, color: "text.secondary" }}>
                    <VideoLibraryIcon sx={{ fontSize: 48, color: "text.disabled", mb: 1.5 }} />
                    <Typography variant="h6" sx={{ mb: 0.5 }}>No generated videos yet</Typography>
                    <Typography variant="body2" sx={{ mb: 0.5 }}>
                      Create your first video from a competitor analysis or from your own script.
                    </Typography>
                    <Typography variant="caption" sx={{ display: "block", mb: 2.5, color: "text.disabled" }}>
                      Pexels stock footage matched to your script — free, fast, and runs locally.
                    </Typography>
                    <Stack direction="row" spacing={1.5} justifyContent="center">
                      <Button variant="contained" color="secondary" startIcon={<PhotoLibraryIcon />}
                        onClick={() => navigate("/stock")}>Create Stock Video</Button>
                    </Stack>
                  </Box>
                ) : (
                  <>
                  <Stack spacing={0}>
                    {generatedVideos.map(v => {
                      const isExpanded = expandedId === v.id
                      return (
                        <Fragment key={v.id}>
                          <Paper
                            elevation={0}
                            onClick={() => toggleExpand(v.id, async () => {
                              try {
                                const r = await http.get(`/api/videos/${v.id}`)
                                setDetailVideo({ ...r.data, _type: "generated" })
                              } catch { showSnackbar("Failed to load video details", "error") }
                            })}
                            sx={{
                              px: 2, py: 1.5, mb: isExpanded ? 0 : 0.75,
                              border: 1,
                              borderColor: isExpanded ? "secondary.main" : "divider",
                              borderRadius: isExpanded ? "12px 12px 0 0" : 3,
                              cursor: "pointer",
                              display: "flex", alignItems: "center", gap: 1.5,
                              transition: "all 0.15s ease",
                              "&:hover": { borderColor: "secondary.light", bgcolor: "action.hover" },
                            }}
                          >
                            {/* Thumbnail */}
                            <Box sx={{
                              width: 80, height: 52, borderRadius: 1.5, overflow: "hidden",
                              bgcolor: "action.hover", flexShrink: 0,
                              display: "flex", alignItems: "center", justifyContent: "center",
                            }}>
                              {v.thumbnail_path ? (
                                <Box component="img" src={`/api/videos/${v.id}/thumbnail`} alt=""
                                  sx={{ width: "100%", height: "100%", objectFit: "cover" }} />
                              ) : (
                                <MovieCreationIcon sx={{ color: "text.disabled", fontSize: 20 }} />
                              )}
                            </Box>

                            <Box sx={{ flex: 1, minWidth: 0 }}>
                              <Typography variant="body1" sx={{ fontWeight: 500, fontSize: "0.95rem" }} noWrap>
                                {v.title || "Untitled"}
                              </Typography>
                              <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.25 }}>
                                <Chip label={v.status} size="small" color={STATUS_COLOR[v.status] || "default"}
                                  sx={{ height: 20, fontSize: "0.65rem" }} />
                                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                                  {v.source_type === "clip_extraction" ? "Clip" : "Stock"} · {v.aspect_ratio}
                                  {v.duration_seconds ? ` · ${Math.floor(v.duration_seconds / 60)}:${String(v.duration_seconds % 60).padStart(2, "0")}` : ""}
                                </Typography>
                                {v.clip_virality_score != null && (
                                  <Chip icon={<WhatshotIcon />} label={`${v.clip_virality_score.toFixed(1)}`}
                                    size="small" variant="filled"
                                    color={v.clip_virality_score >= 8 ? "success" : v.clip_virality_score >= 6 ? "warning" : "default"}
                                    sx={{ height: 20, fontSize: "0.65rem" }} />
                                )}
                                {v.caption_status === "failed" && (
                                  <Chip icon={<WarningAmberIcon />} label="No captions" size="small" color="warning"
                                    sx={{ height: 20, fontSize: "0.65rem" }} />
                                )}
                              </Stack>
                            </Box>

                            {v.status === "ready" && (
                              <Stack direction="row" spacing={0.5} sx={{ flexShrink: 0 }}>
                                <Button size="small" color="error" variant="contained"
                                  onClick={e => { e.stopPropagation(); openUploadPreview(v.id, ["youtube"]) }}>
                                  YouTube
                                </Button>
                                <Button size="small" color="info" variant="contained"
                                  onClick={e => { e.stopPropagation(); openUploadPreview(v.id, ["tiktok"]) }}>
                                  TikTok
                                </Button>
                              </Stack>
                            )}

                            <IconButton size="small" sx={{ color: "text.secondary" }}>
                              {isExpanded ? <ExpandLessIcon /> : <ExpandMoreIcon />}
                            </IconButton>
                          </Paper>

                          <Collapse in={isExpanded} unmountOnExit>
                            {detailVideo?._type === "generated" && detailVideo.id === v.id && (
                              <GeneratedDetail
                                video={detailVideo}
                                onUpload={openUploadPreview}
                                onDelete={(id) => openConfirm("Delete generated video?", "This will permanently remove the video file and its metadata.", () => handleDeleteVideo(id))}
                                onClose={() => { setExpandedId(null); setDetailVideo(null) }}
                                onDetailUpdate={(updated) => setDetailVideo({ ...updated, _type: "generated" })}
                              />
                            )}
                          </Collapse>
                        </Fragment>
                      )
                    })}
                  </Stack>
                  <TablePagination
                    component="div"
                    count={genTotal}
                    page={genPage}
                    onPageChange={(_, p) => { setGenPage(p); fetchGenerated(p * genRowsPerPage, genRowsPerPage) }}
                    rowsPerPage={genRowsPerPage}
                    onRowsPerPageChange={(e) => { const rpp = parseInt(e.target.value, 10); setGenRowsPerPage(rpp); setGenPage(0); fetchGenerated(0, rpp) }}
                    rowsPerPageOptions={[10, 20, 50]}
                    sx={{ borderTop: 1, borderColor: "divider", mt: 1 }}
                  />
                  </>
                )}
              </>
            )}

            {/* ──── Tab 3: Job History ──── */}
            {tab === 3 && <JobHistoryTab jobs={jobs} jobTotal={jobTotal}
              onDelete={handleDeleteJob}
              onBulkDelete={handleBulkDeleteJobs}
              onCancel={handleCancelJob}
              page={jobPage} rowsPerPage={jobRowsPerPage}
              onPageChange={(_, p) => { setJobPage(p); fetchJobs(jobRowsPerPage, p * jobRowsPerPage) }}
              onRowsPerPageChange={(e) => { const rpp = parseInt(e.target.value, 10); setJobRowsPerPage(rpp); setJobPage(0); fetchJobs(rpp, 0) }}
            />}
          </>
        )}
      </Box>

      {/* Create mode picker menu */}
      <CreateModeMenu
        anchorEl={createMenuAnchor}
        onClose={() => { setCreateMenuAnchor(null); setCreateMenuSourceId(null) }}
        sourceId={createMenuSourceId}
        navigate={navigate}
      />

      {/* Delete confirmation dialog */}
      <Dialog open={confirmDialog.open} onClose={closeConfirm} maxWidth="xs" fullWidth>
        <DialogTitle>{confirmDialog.title}</DialogTitle>
        <DialogContent><Typography>{confirmDialog.message}</Typography></DialogContent>
        <DialogActions>
          <Button onClick={closeConfirm}>Cancel</Button>
          <Button color="error" variant="contained" onClick={() => { confirmDialog.onConfirm?.(); closeConfirm() }}>Delete</Button>
        </DialogActions>
      </Dialog>

      {/* Upload confirmation dialog */}
      <Dialog open={uploadPreview.open} onClose={() => setUploadPreview(prev => ({ ...prev, open: false }))} maxWidth="sm" fullWidth>
        <DialogTitle>Confirm Upload to {uploadPreview.platforms.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(", ")}</DialogTitle>
        <DialogContent>
          {uploadPreview.video && (
            <Stack spacing={1.5} sx={{ pt: 1 }}>
              {uploadPreview.platforms.includes("youtube") && (<>
                <Typography variant="caption" color="text.secondary">YouTube Title</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{uploadPreview.video.youtube_title || uploadPreview.video.title || "(untitled)"}</Typography>
                <Typography variant="caption" color="text.secondary">YouTube Description</Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto", color: "text.secondary" }}>
                  {uploadPreview.video.youtube_description || "(no description)"}
                </Typography>
              </>)}
              {uploadPreview.platforms.includes("tiktok") && (<>
                <Typography variant="caption" color="text.secondary">TikTok Title</Typography>
                <Typography variant="body2" sx={{ fontWeight: 600 }}>{uploadPreview.video.tiktok_title || uploadPreview.video.title || "(untitled)"}</Typography>
                <Typography variant="caption" color="text.secondary">TikTok Description</Typography>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", maxHeight: 120, overflow: "auto", color: "text.secondary" }}>
                  {uploadPreview.video.tiktok_description || "(no description)"}
                </Typography>
              </>)}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadPreview(prev => ({ ...prev, open: false }))}>Cancel</Button>
          <Button variant="contained" onClick={() => { handleUpload(uploadPreview.videoId, uploadPreview.platforms); setUploadPreview(prev => ({ ...prev, open: false })) }}>
            Upload
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
