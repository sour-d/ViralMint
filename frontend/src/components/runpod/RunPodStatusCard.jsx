import { useState, useEffect, useCallback, useMemo } from "react"
import { Link as RouterLink } from "react-router-dom"
import {
  Box, Stack, Typography, Button, Chip, Paper, CircularProgress, Link, Alert,
  LinearProgress,
} from "@mui/material"
import CloudQueueIcon from "@mui/icons-material/CloudQueue"
import OpenInNewIcon from "@mui/icons-material/OpenInNew"
import PlayArrowIcon from "@mui/icons-material/PlayArrow"
import DownloadIcon from "@mui/icons-material/Download"
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline"
import http from "../../api/http"
import useAppStore from "../../store/appStore"

const SETUP_JOB_TYPE = "runpod_install_models"
const POLL_ACTIVE_MS = 2500
const POLL_WAITING_MS = 12000

const STATE_COLORS = {
  none: "default",
  starting: "warning",
  running: "info",
  stopped: "default",
  error: "error",
}

const STATE_LABELS = {
  none: "No pod",
  starting: "Starting…",
  running: "Running",
  stopped: "Stopped",
  error: "Error",
}

export default function RunPodStatusCard({ onReadyChange }) {
  const showSnackbar = useAppStore((s) => s.showSnackbar)
  const startJob = useAppStore((s) => s.startJob)
  const activeJobs = useAppStore((s) => s.activeJobs)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(null)

  const setupJob = useMemo(
    () => Object.values(activeJobs).find(
      (j) => j.jobType === SETUP_JOB_TYPE && j.status === "running",
    ),
    [activeJobs],
  )

  const needsFastPoll = Boolean(
    busy || setupJob || status?.setup_in_progress || status?.pod_state === "starting",
  )
  const pollIntervalMs = useMemo(() => {
    if (!status || status.pod_state === "error") return null
    if (needsFastPoll) return POLL_ACTIVE_MS
    if (status.can_generate) return null
    if (status.configured) return POLL_WAITING_MS
    return null
  }, [status, needsFastPoll])

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await http.get("/api/runpod/status")
      setStatus(data)
      onReadyChange?.(!!data.can_generate)
    } catch (err) {
      const detail = err.response?.data?.detail || err.message
      setStatus({
        configured: false,
        pod_state: "error",
        message: detail,
        activity_line: detail,
        can_deploy: false,
        can_generate: false,
      })
      onReadyChange?.(false)
    } finally {
      setLoading(false)
    }
  }, [onReadyChange])

  useEffect(() => {
    fetchStatus()
  }, [fetchStatus])

  const isActive = Boolean(needsFastPoll)

  useEffect(() => {
    if (pollIntervalMs == null) return undefined
    const id = setInterval(fetchStatus, pollIntervalMs)
    return () => clearInterval(id)
  }, [pollIntervalMs, fetchStatus])

  useEffect(() => {
    const onFocus = () => {
      if (pollIntervalMs == null) fetchStatus()
    }
    window.addEventListener("focus", onFocus)
    return () => window.removeEventListener("focus", onFocus)
  }, [pollIntervalMs, fetchStatus])

  const activityLine = useMemo(() => {
    if (busy === "deploy") return "Deploying RunPod GPU pod…"
    if (busy === "setup") return "Starting pod setup…"
    if (setupJob?.step) {
      const pct = setupJob.percent
      return pct > 0 ? `${setupJob.step} (${Math.round(pct)}%)` : setupJob.step
    }
    return status?.activity_line || status?.message || (loading ? "Checking RunPod status…" : "")
  }, [busy, setupJob, status, loading])

  const progressPct = setupJob?.percent ?? status?.setup_job?.progress_pct ?? 0
  const showProgress = Boolean(
    busy === "setup" || setupJob || (status?.setup_job && !status?.can_generate),
  )

  const handleDeploy = async () => {
    setBusy("deploy")
    try {
      const { data } = await http.post("/api/runpod/deploy")
      showSnackbar(data.message || "Pod deployment started", "success")
      await fetchStatus()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setBusy(null)
    }
  }

  const handleSetup = async () => {
    setBusy("setup")
    try {
      const { data } = await http.post("/api/runpod/setup")
      if (data.skipped) {
        showSnackbar(data.message || "Pod already set up", "success")
      } else if (data.job_id) {
        startJob(data.job_id, SETUP_JOB_TYPE, data.message || "Setting up pod…")
        showSnackbar(data.message || "Setup started", "info")
      } else {
        showSnackbar(data.message || "Setup finished", "info")
      }
      await fetchStatus()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setBusy(null)
    }
  }

  const handleCleanup = async () => {
    const ok = window.confirm(
      "Remove LTX workflow setup from this pod?\n\n"
      + "• Uninstalls ComfyUI-LTXVideo and ComfyMath custom nodes\n"
      + "• Lists ~45GB of model files for you to delete on the pod (not deleted automatically)\n\n"
      + "Type OK to continue.",
    )
    if (!ok) return
    setBusy("cleanup")
    try {
      const { data } = await http.post("/api/runpod/cleanup", { confirm: "REMOVE_LTX" })
      const modelPaths = data?.models?.paths || []
      const pathsHint = modelPaths.length
        ? `\n\nModel paths (delete on pod):\n${modelPaths.slice(0, 3).join("\n")}${modelPaths.length > 3 ? "\n…" : ""}`
        : ""
      showSnackbar((data.message || "Cleanup queued") + pathsHint, "warning")
      await fetchStatus()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setBusy(null)
    }
  }

  const podState = status?.pod_state || "none"

  return (
    <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2, mb: 2 }}>
      <Stack direction="row" spacing={1.5} alignItems="flex-start" justifyContent="space-between">
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
          <CloudQueueIcon sx={{ color: "primary.main", fontSize: 28 }} />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
              <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
                RunPod ComfyUI
              </Typography>
              {loading ? (
                <CircularProgress size={16} />
              ) : (
                <Chip
                  size="small"
                  label={STATE_LABELS[podState] || podState}
                  color={STATE_COLORS[podState] || "default"}
                  variant="outlined"
                />
              )}
              {status?.comfy_ready && (
                <Chip size="small" label="ComfyUI up" color="info" variant="outlined" />
              )}
              {status?.custom_nodes_ready && (
                <Chip size="small" label="Nodes ready" color="success" variant="outlined" />
              )}
              {status?.models_ready && (
                <Chip size="small" label="Models ready" color="success" />
              )}
              {status?.can_generate && (
                <Chip size="small" label="Ready to generate" color="success" variant="outlined" />
              )}
            </Stack>

            {activityLine && (
              <Box
                sx={{
                  mt: 1.5,
                  px: 1.25,
                  py: 0.75,
                  borderRadius: 1,
                  bgcolor: (t) => (t.palette.mode === "dark"
                    ? "rgba(255,255,255,0.06)"
                    : "rgba(0,0,0,0.04)"),
                  border: 1,
                  borderColor: "divider",
                }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  {isActive && (
                    <CircularProgress size={12} thickness={5} sx={{ flexShrink: 0 }} />
                  )}
                  <Typography
                    variant="caption"
                    component="div"
                    sx={{
                      fontFamily: "monospace",
                      fontSize: "0.75rem",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                      flex: 1,
                      minWidth: 0,
                    }}
                    title={activityLine}
                  >
                    {activityLine}
                  </Typography>
                </Stack>
                {showProgress && (
                  <LinearProgress
                    variant={progressPct > 0 ? "determinate" : "indeterminate"}
                    value={progressPct > 0 ? progressPct : undefined}
                    sx={{ mt: 0.75, height: 3, borderRadius: 2 }}
                  />
                )}
              </Box>
            )}
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center" flexShrink={0} flexWrap="wrap" useFlexGap>
          {status?.comfy_url && status.comfy_ready && (
            <Button
              size="small"
              variant="outlined"
              endIcon={<OpenInNewIcon />}
              href={status.comfy_url}
              target="_blank"
              rel="noreferrer"
            >
              Open ComfyUI
            </Button>
          )}
          {status?.can_setup && (
            <Button
              size="small"
              variant="outlined"
              startIcon={busy === "setup" ? <CircularProgress size={16} /> : <DownloadIcon />}
              onClick={handleSetup}
              disabled={!!busy}
            >
              {busy === "setup" ? "Starting…" : "Setup pod"}
            </Button>
          )}
          {status?.can_cleanup && (
            <Button
              size="small"
              variant="outlined"
              color="warning"
              startIcon={busy === "cleanup" ? <CircularProgress size={16} /> : <DeleteOutlineIcon />}
              onClick={handleCleanup}
              disabled={!!busy}
            >
              {busy === "cleanup" ? "Removing…" : "Remove LTX setup"}
            </Button>
          )}
          {status?.can_deploy && !status?.comfy_ready && (
            <Button
              size="small"
              variant="contained"
              startIcon={busy === "deploy" ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
              onClick={handleDeploy}
              disabled={!!busy || !status?.configured}
            >
              {busy === "deploy" ? "Deploying…" : "Deploy Pod"}
            </Button>
          )}
        </Stack>
      </Stack>

      {!status?.configured && !loading && (
        <Alert severity="info" sx={{ mt: 2 }}>
          Add your RunPod API key in{" "}
          <Link component={RouterLink} to="/settings">Settings</Link>
          {" "}or set <code>RUNPOD_API_KEY</code> in <code>.env</code>.
        </Alert>
      )}

      {status?.comfy_ready && status?.can_setup && !setupJob && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <strong>Setup pod</strong> only downloads or installs what is missing (safe to click again).
          Uses RunpodDirect like ComfyUI &quot;Download to Pod&quot;. Restart ComfyUI after new node installs.
        </Alert>
      )}
      {status?.comfy_ready && status?.can_generate && !setupJob && (
        <Alert severity="success" sx={{ mt: 2 }}>
          Pod is ready. Setup will not re-download models or reinstall nodes unless something is missing.
        </Alert>
      )}
    </Paper>
  )
}
