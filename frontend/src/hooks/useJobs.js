import { useEffect, useRef, useState } from "react"
import http from "../api/http"
import useAppStore from "../store/appStore"

export default function useJobs(pollInterval = 5000) {
  const jobs = useAppStore((s) => s.jobs)
  const setJobs = useAppStore((s) => s.setJobs)
  const [jobTotal, setJobTotal] = useState(0)
  const timerRef = useRef(null)

  const fetchJobs = async (limit = 20, offset = 0) => {
    try {
      const { data } = await http.get("/api/jobs", { params: { limit, offset } })
      setJobs(data.jobs || [])
      setJobTotal(data.total || 0)
    } catch (err) {
      console.error("Failed to fetch jobs:", err)
    }
  }

  useEffect(() => {
    fetchJobs()
    timerRef.current = setInterval(() => fetchJobs(), pollInterval)
    return () => clearInterval(timerRef.current)
  }, [pollInterval])

  return { jobs, jobTotal, fetchJobs }
}
