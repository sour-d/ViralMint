import { useMemo } from "react"
import { Navigate, useParams, Link as RouterLink } from "react-router-dom"
import {
  Box, Stack, Typography, Paper, Button, Chip, Card, CardContent,
} from "@mui/material"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import ArrowForwardIcon from "@mui/icons-material/ArrowForward"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import { creatorNiches } from "../data/creatorNiches"

export default function CreatorNiche() {
  const { slug } = useParams()
  const niche = useMemo(() => creatorNiches.find((item) => item.slug === slug), [slug])

  if (!niche) {
    return <Navigate to="/creator" replace />
  }

  // Dedicated studio pages
  if (slug === "niche1") return <Navigate to="/niche1" replace />
  if (slug === "niche2") return <Navigate to="/niche2" replace />

  const angleIdeas = [
    "Strong hook in the first 2 seconds",
    "Fast visual beats with no dead air",
    "One clear takeaway or opinion",
  ]

  return (
    <Box sx={{ height: "100%", overflow: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1180, mx: "auto" }}>
        <Paper
          variant="outlined"
          sx={{
            p: { xs: 2.5, md: 3 },
            borderRadius: 3,
            background: (t) => t.palette.mode === "dark"
              ? `linear-gradient(135deg, ${niche.accent}20 0%, rgba(15,23,42,1) 72%)`
              : `linear-gradient(135deg, ${niche.accent}12 0%, rgba(255,255,255,1) 72%)`,
          }}
        >
          <Stack spacing={1.5} sx={{ maxWidth: 760 }}>
            <Chip
              icon={<AutoAwesomeIcon sx={{ fontSize: 16 }} />}
              label={niche.label}
              variant="outlined"
              sx={{ width: "fit-content" }}
            />
            <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.6, lineHeight: 1.05 }}>
              {niche.label} content lane
            </Typography>
            <Typography sx={{ color: "text.secondary", maxWidth: 700, lineHeight: 1.7 }}>
              {niche.description}
            </Typography>
            <Button
              component={RouterLink}
              to={`/ai-video?preset=${encodeURIComponent(niche.slug)}`}
              variant="contained"
              startIcon={<MovieCreationIcon />}
              sx={{ width: "fit-content", borderRadius: 2, fontWeight: 700, textTransform: "none" }}
            >
              Open generator with this niche
            </Button>
          </Stack>
        </Paper>

        <Stack direction={{ xs: "column", md: "row" }} spacing={2}>
          <Card variant="outlined" sx={{ flex: 1 }}>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle2" sx={{ color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.6 }}>
                Prompt seed
              </Typography>
              <Typography sx={{ mt: 1.25, lineHeight: 1.8 }}>
                {niche.promptSeed}
              </Typography>
            </CardContent>
          </Card>

          <Card variant="outlined" sx={{ flex: 1 }}>
            <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
              <Typography variant="subtitle2" sx={{ color: "text.secondary", textTransform: "uppercase", letterSpacing: 0.6 }}>
                Next move
              </Typography>
              <Stack spacing={1} sx={{ mt: 1.25 }}>
                {angleIdeas.map((idea) => (
                  <Typography key={idea} variant="body2" sx={{ color: "text.secondary" }}>
                    {idea}
                  </Typography>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Stack>

        <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3 }}>
          <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 1.5 }}>
            <ArrowForwardIcon sx={{ color: "primary.main" }} />
            <Typography variant="h6" sx={{ fontWeight: 700 }}>
              Quick actions
            </Typography>
          </Stack>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
            <Button
              component={RouterLink}
              to="/comfyui"
              variant="outlined"
              sx={{ textTransform: "none", fontWeight: 700 }}
            >
              Check setup status
            </Button>
            <Button
              component={RouterLink}
              to="/videos"
              variant="outlined"
              sx={{ textTransform: "none", fontWeight: 700 }}
            >
              Open library
            </Button>
          </Stack>
        </Paper>
      </Stack>
    </Box>
  )
}
