import { useEffect } from "react"
import { ws } from "../api/websocket"
import useAppStore from "../store/appStore"

export default function useWebSocket() {
  const {
    showSnackbar,
    startJob,
    updateJobProgress,
    completeJob,
    failJob,
    removeJob,
  } = useAppStore()

  useEffect(() => {
    ws.connect()

    const unsubs = [
      ws.on("job_started", (msg) => {
        startJob(msg.job_id, msg.job_type, msg.message, { inputData: msg.input_data || null })
      }),

      ws.on("job_progress", (msg) => {
        updateJobProgress(msg.job_id, msg.percent, msg.step)
      }),

      ws.on("job_complete", (msg) => {
        completeJob(msg.job_id)
        const result = msg.result || {}
        const jobInfo = useAppStore.getState().activeJobs[msg.job_id]
        const jobType = jobInfo?.type || msg.job_type || ""

        if (jobType === "anime_lofi_generate_images" || jobType === "anime_lofi_generate_videos") {
          setTimeout(() => removeJob(msg.job_id), 10000)
          showSnackbar("Generation complete!", "success")
          return
        }

        setTimeout(() => removeJob(msg.job_id), 10000)
      }),

      ws.on("job_failed", (msg) => {
        failJob(msg.job_id, msg.error)
        showSnackbar(msg.error || "A job failed", "error")
      }),
    ]

    return () => {
      unsubs.forEach(fn => fn())
    }
  }, [])
}
