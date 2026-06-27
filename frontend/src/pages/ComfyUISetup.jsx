import { useEffect, useRef, useState, useCallback } from "react"
import {
  Box, Stack, Typography, Paper, Button, Chip, Alert, Grid,
  List, ListItem, ListItemIcon, ListItemText, LinearProgress,
} from "@mui/material"
import CloudQueueIcon from "@mui/icons-material/CloudQueue"
import CheckCircleIcon from "@mui/icons-material/CheckCircle"
import CancelIcon from "@mui/icons-material/Cancel"
import DownloadIcon from "@mui/icons-material/Download"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import VideoLibraryIcon from "@mui/icons-material/VideoLibrary"
import ImageIcon from "@mui/icons-material/Image"
import http from "../api/http"
import RunPodStatusCard from "../components/runpod/RunPodStatusCard"
import useAppStore from "../store/appStore"

function WorkflowCard({ workflow, title, icon, loading, setupType, onRefresh }) {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const [busy, setBusy] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [modelsStatus, setModelsStatus] = useState(null)
  const pollRef = useRef(null)

  // Poll model download status while pod is running
  const fetchModelsStatus = useCallback(async () => {
    try {
      const { data } = await http.get(`/api/runpod/models-status?type=${setupType}`)
      setModelsStatus(data)
    } catch {
      // pod not ready — ignore
    }
  }, [setupType])

  useEffect(() => {
    fetchModelsStatus()
    pollRef.current = setInterval(fetchModelsStatus, 8000)
    return () => clearInterval(pollRef.current)
  }, [fetchModelsStatus])

  const handleDownload = async () => {
    setBusy(true)
    try {
      const { data } = await http.post(`/api/runpod/setup?type=${setupType}`)
      if (data.skipped) {
        showSnackbar(data.message || "Already set up", "success")
      } else if (data.job_id) {
        showSnackbar(data.message, "info")
      } else {
        showSnackbar(data.message || "Setup complete", "success")
      }
      // Keep polling modelsStatus so the count updates
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setBusy(false)
      onRefresh()
    }
  }

  const handleDelete = async () => {
    const label = title
    const ok = window.confirm(
      `Remove ${label} model files from the pod?\n\n`
      + `ViralMint cannot delete large files via API — the file paths will be shown. `
      + `You must delete them manually in the RunPod file browser or terminal.`
    )
    if (!ok) return
    setDeleting(true)
    try {
      const { data } = await http.post(`/api/runpod/delete-models?type=${setupType}`)
      const paths = data?.paths || []
      const hint = paths.length
        ? `\n\nPaths (delete on pod):\n${paths.slice(0, 3).join("\n")}${paths.length > 3 ? "\n…" : ""}`
        : ""
      showSnackbar((data.message || "No models to delete") + hint, "warning")
      await fetchModelsStatus()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return (
      <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: "100%" }}>
        <Stack spacing={1.5}>
          <Stack direction="row" spacing={1} alignItems="center">
            {icon}
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{title}</Typography>
          </Stack>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>Loading…</Typography>
        </Stack>
      </Paper>
    )
  }

  const checks = [
    {
      label: "Workflow file",
      ok: Boolean(workflow?.workflow_file),
      detail: workflow?.workflow_file || "missing",
    },
    {
      label: "Mapping configured",
      ok: workflow?.configured,
      detail: workflow?.configured ? "Node IDs set" : "Need setup",
    },
  ]

  const modelCount = workflow?.required_models?.length || 0
  const presentCount = modelsStatus?.present_count ?? 0
  const totalCount = modelsStatus?.total ?? modelCount
  const allDownloaded = totalCount > 0 && presentCount >= totalCount

  checks.push({
    label: "Models downloaded",
    ok: allDownloaded,
    detail: totalCount > 0 ? `${presentCount} / ${totalCount}` : "0",
  })

  // Show model filenames (color-coded)
  const models = workflow?.required_models || []
  const presentFilenames = new Set((modelsStatus?.present || []).map((m) => m.filename))
  const missingFilenames = new Set((modelsStatus?.missing || []).map((m) => m.filename))

  return (
    <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: "100%" }}>
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
          <Stack direction="row" spacing={1} alignItems="center">
            {icon}
            <Typography variant="h6" sx={{ fontWeight: 700 }}>{title}</Typography>
          </Stack>
          {workflow?.configured && allDownloaded && (
            <Chip size="small" label="Ready" color="success" />
          )}
        </Stack>

        <List dense disablePadding>
          {checks.map((c) => (
            <ListItem key={c.label} disableGutters sx={{ py: 0.25 }}>
              <ListItemIcon sx={{ minWidth: 32 }}>
                {c.ok
                  ? <CheckCircleIcon sx={{ fontSize: 18, color: "success.main" }} />
                  : <CancelIcon sx={{ fontSize: 18, color: "warning.main" }} />
                }
              </ListItemIcon>
              <ListItemText
                primary={c.label}
                secondary={c.detail}
                primaryTypographyProps={{ variant: "body2", fontWeight: 600 }}
                secondaryTypographyProps={{ variant: "caption" }}
              />
            </ListItem>
          ))}
        </List>

        {models.length > 0 && (
          <Box sx={{ px: 0.5 }}>
            {models.map((m) => {
              const isPresent = presentFilenames.has(m.filename)
              const isMissing = missingFilenames.has(m.filename)
              const color = isPresent ? "success.main" : isMissing ? "warning.main" : "text.secondary"
              return (
                <Typography
                  key={m.filename}
                  variant="caption"
                  sx={{ display: "block", color, lineHeight: 1.6, fontWeight: isPresent ? 600 : 400 }}
                >
                  {isPresent ? "✓ " : ""}{m.folder}/{m.filename}
                </Typography>
              )
            })}
          </Box>
        )}

        {busy && (
          <LinearProgress
            variant="indeterminate"
            sx={{ height: 4, borderRadius: 2 }}
          />
        )}

        <Stack direction="row" spacing={1}>
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleDownload}
            disabled={busy}
            size="small"
            sx={{ borderRadius: 2, fontWeight: 600, textTransform: "none", flex: 1 }}
          >
            {busy ? "Downloading…" : "Download Models"}
          </Button>
          {totalCount > 0 && (
            <Button
              variant="outlined"
              color="warning"
              startIcon={<DeleteOutlineIcon />}
              onClick={handleDelete}
              disabled={deleting}
              size="small"
              sx={{ borderRadius: 2, fontWeight: 600, textTransform: "none", minWidth: 40 }}
              title="Delete models for this workflow"
            >
              {deleting ? "…" : <DeleteOutlineIcon fontSize="small" />}
            </Button>
          )}
        </Stack>
      </Stack>
    </Paper>
  )
}

export default function ComfyUISetup() {
  const [ltx, setLtx] = useState(null)
  const [ltxImg2vid, setLtxImg2vid] = useState(null)
  const [niche2, setNiche2] = useState(null)
  const [loadingLtx, setLoadingLtx] = useState(true)
  const [loadingLtxImg2vid, setLoadingLtxImg2vid] = useState(true)
  const [loadingNiche2, setLoadingNiche2] = useState(true)

  const fetchLtx = useCallback(async () => {
    try {
      const { data } = await http.get("/api/runpod/workflow?type=ltx")
      setLtx(data)
    } finally {
      setLoadingLtx(false)
    }
  }, [])
  const fetchLtxImg2vid = useCallback(async () => {
    try {
      const { data } = await http.get("/api/runpod/workflow?type=ltx-img2vid")
      setLtxImg2vid(data)
    } finally {
      setLoadingLtxImg2vid(false)
    }
  }, [])
  const fetchNiche2 = useCallback(async () => {
    try {
      const { data } = await http.get("/api/runpod/workflow?type=z-turbo")
      setNiche2(data)
    } finally {
      setLoadingNiche2(false)
    }
  }, [])

  useEffect(() => {
    fetchLtx()
    fetchLtxImg2vid()
    fetchNiche2()
  }, [fetchLtx, fetchLtxImg2vid, fetchNiche2])

  return (
    <Box sx={{ height: "100%", overflow: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1200, mx: "auto" }}>
        <Paper variant="outlined" sx={{
          p: { xs: 2.5, md: 3 }, borderRadius: 3,
          background: (t) => t.palette.mode === "dark"
            ? "linear-gradient(135deg, rgba(37,99,235,0.16) 0%, rgba(15,23,42,1) 72%)"
            : "linear-gradient(135deg, rgba(37,99,235,0.08) 0%, rgba(255,255,255,1) 72%)",
        }}>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Box sx={{ width: 42, height: 42, borderRadius: 2, bgcolor: "primary.main", color: "#fff", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <CloudQueueIcon />
            </Box>
            <Box>
              <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.6 }}>ComfyUI Setup</Typography>
              <Typography sx={{ color: "text.secondary", mt: 0.5, lineHeight: 1.6 }}>
                Deploy your pod, then download models for each workflow separately.
              </Typography>
            </Box>
          </Stack>
        </Paper>

        <RunPodStatusCard />

        <Grid container spacing={2}>
          <Grid item xs={12} md={4}>
            <WorkflowCard
              workflow={ltx}
              title="LTX Audio→Video"
              icon={<VideoLibraryIcon sx={{ color: "primary.main", fontSize: 24 }} />}
              loading={loadingLtx}
              setupType="ltx"
              onRefresh={fetchLtx}
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <WorkflowCard
              workflow={ltxImg2vid}
              title="LTX Image→Video"
              icon={<VideoLibraryIcon sx={{ color: "secondary.main", fontSize: 24 }} />}
              loading={loadingLtxImg2vid}
              setupType="ltx-img2vid"
              onRefresh={fetchLtxImg2vid}
            />
          </Grid>
          <Grid item xs={12} md={4}>
            <WorkflowCard
              workflow={niche2}
              title="Z-turbo Image"
              icon={<ImageIcon sx={{ color: "primary.main", fontSize: 24 }} />}
              loading={loadingNiche2}
              setupType="z-turbo"
              onRefresh={fetchNiche2}
            />
          </Grid>
        </Grid>
      </Stack>
    </Box>
  )
}
