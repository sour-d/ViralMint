import { create } from "zustand"

const useAppStore = create((set) => ({
  // Active jobs — real-time via WebSocket
  activeJobs: {},
  startJob: (jobId, jobType, message, meta) => set((s) => ({
    activeJobs: {
      ...s.activeJobs,
      [jobId]: { jobId, jobType, status: "running", percent: 0, step: message || "", message, startedAt: Date.now(), ...(meta || {}) },
    },
  })),
  updateJobProgress: (jobId, percent, step) => set((s) => {
    const existing = s.activeJobs[jobId]
    if (!existing) return {}
    return { activeJobs: { ...s.activeJobs, [jobId]: { ...existing, percent, step } } }
  }),
  completeJob: (jobId) => set((s) => {
    const existing = s.activeJobs[jobId]
    if (!existing) return {}
    return { activeJobs: { ...s.activeJobs, [jobId]: { ...existing, status: "success", percent: 100 } } }
  }),
  failJob: (jobId, error) => set((s) => {
    const existing = s.activeJobs[jobId]
    if (!existing) return {}
    return { activeJobs: { ...s.activeJobs, [jobId]: { ...existing, status: "failed", step: error || "Failed" } } }
  }),
  removeJob: (jobId) => set((s) => {
    const { [jobId]: _, ...rest } = s.activeJobs
    return { activeJobs: rest }
  }),

  // Global snackbar
  snackbar: { open: false, message: "", severity: "info", action: null },
  showSnackbar: (message, severity = "info", action = null) => set({ snackbar: { open: true, message, severity, action } }),
  closeSnackbar: () => set((s) => ({ snackbar: { ...s.snackbar, open: false } })),
}))

export default useAppStore
