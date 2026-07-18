import { useMemo } from "react"
import { Navigate, useParams } from "react-router-dom"
import { creatorNiches } from "../data/creatorNiches"

export default function CreatorNiche() {
  const { slug } = useParams()
  const niche = useMemo(() => creatorNiches.find((item) => item.slug === slug), [slug])

  if (!niche) {
    return <Navigate to="/creator" replace />
  }

  if (slug === "anime-lofi") return <Navigate to="/anime-lofi" replace />

  return <Navigate to="/creator" replace />
}
