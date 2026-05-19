import { useState, useEffect, useCallback } from "react"
import { Link as RouterLink } from "react-router-dom"
import {
  Box, Stack, Typography, Button, Chip, Paper, CircularProgress, Link, Alert,
} from "@mui/material"
import CloudQueueIcon from "@mui/icons-material/CloudQueue"
import OpenInNewIcon from "@mui/icons-material/OpenInNew"
import PlayArrowIcon from "@mui/icons-material/PlayArrow"
import http from "../../api/http"
import useAppStore from "../../store/appStore"

const POLL_MS = 5000

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
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [deploying, setDeploying] = useState(false)

  const fetchStatus = useCallback(async () => {
    try {
      const { data } = await http.get("/api/runpod/status")
      setStatus(data)
      onReadyChange?.(!!data.comfy_ready)
    } catch (err) {
      setStatus({
        configured: false,
        pod_state: "error",
        message: err.response?.data?.detail || err.message,
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

  useEffect(() => {
    if (!status || status.comfy_ready || status.pod_state === "none" || status.pod_state === "stopped") {
      return undefined
    }
    const id = setInterval(fetchStatus, POLL_MS)
    return () => clearInterval(id)
  }, [status, fetchStatus])

  const handleDeploy = async () => {
    setDeploying(true)
    try {
      const { data } = await http.post("/api/runpod/deploy")
      showSnackbar(data.message || "Pod deployment started", "success")
      await fetchStatus()
    } catch (err) {
      showSnackbar(err.response?.data?.detail || err.message, "error")
    } finally {
      setDeploying(false)
    }
  }

  const podState = status?.pod_state || "none"
  const showDeploy = status?.can_deploy && !status?.comfy_ready

  return (
    <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 2, mb: 2 }}>
      <Stack direction="row" spacing={1.5} alignItems="flex-start" justifyContent="space-between">
        <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
          <CloudQueueIcon sx={{ color: "primary.main", fontSize: 28 }} />
          <Box sx={{ minWidth: 0 }}>
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
                <Chip size="small" label="Ready" color="success" />
              )}
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {status?.message || "Checking RunPod status…"}
            </Typography>
            {status?.cost_per_hr && (
              <Typography variant="caption" color="text.secondary">
                ~${status.cost_per_hr}/hr while running
              </Typography>
            )}
          </Box>
        </Stack>

        <Stack direction="row" spacing={1} alignItems="center" flexShrink={0}>
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
          {showDeploy && (
            <Button
              size="small"
              variant="contained"
              startIcon={deploying ? <CircularProgress size={16} color="inherit" /> : <PlayArrowIcon />}
              onClick={handleDeploy}
              disabled={deploying || !status?.configured}
            >
              {deploying ? "Deploying…" : "Deploy Pod"}
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
    </Paper>
  )
}
