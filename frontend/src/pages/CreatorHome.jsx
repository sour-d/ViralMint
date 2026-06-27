import { Link as RouterLink } from "react-router-dom"
import {
  Box, Stack, Typography, Paper, Button, Card, CardContent, Grid, Chip,
} from "@mui/material"
import ArrowForwardIcon from "@mui/icons-material/ArrowForward"
import AutoAwesomeIcon from "@mui/icons-material/AutoAwesome"
import CloudQueueIcon from "@mui/icons-material/CloudQueue"
import MovieCreationIcon from "@mui/icons-material/MovieCreation"
import TrendingUpIcon from "@mui/icons-material/TrendingUp"
import { creatorNiches } from "../data/creatorNiches"

const steps = [
  "Deploy the ComfyUI pod",
  "Install the LTX workflow models",
  "Pick a niche and open a short-video brief",
  "Generate, review, and iterate",
]

export default function CreatorHome() {
  return (
    <Box sx={{ height: "100%", overflow: "auto", p: { xs: 2, md: 3 } }}>
      <Stack spacing={3} sx={{ maxWidth: 1180, mx: "auto" }}>
        <Paper
          variant="outlined"
          sx={{
            p: { xs: 2.5, md: 3 },
            borderRadius: 3,
            overflow: "hidden",
            background: (t) => t.palette.mode === "dark"
              ? "linear-gradient(135deg, rgba(13,159,110,0.14) 0%, rgba(15,23,42,1) 70%)"
              : "linear-gradient(135deg, rgba(13,159,110,0.10) 0%, rgba(255,255,255,1) 70%)",
          }}
        >
          <Stack spacing={1.5} sx={{ maxWidth: 760 }}>
            <Chip
              icon={<AutoAwesomeIcon sx={{ fontSize: 16 }} />}
              label="Short-form creator workspace"
              color="primary"
              variant="outlined"
              sx={{ width: "fit-content" }}
            />
            <Typography variant="h4" sx={{ fontWeight: 800, letterSpacing: -0.6, lineHeight: 1.05 }}>
              Build a focused AI video studio for one niche at a time.
            </Typography>
            <Typography sx={{ color: "text.secondary", maxWidth: 680, lineHeight: 1.7 }}>
              This workspace is trimmed down for short video creation: set up ComfyUI, load the LTX workflow,
              download the missing models, then jump into the niche tabs you want to grow.
            </Typography>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5}>
              <Button
                component={RouterLink}
                to="/comfyui"
                variant="contained"
                startIcon={<CloudQueueIcon />}
                sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
              >
                Go to ComfyUI Setup
              </Button>
              <Button
                component={RouterLink}
                to={`/niche/${creatorNiches[0].slug}`}
                variant="outlined"
                startIcon={<MovieCreationIcon />}
                sx={{ borderRadius: 2, fontWeight: 700, textTransform: "none" }}
              >
                Start With a Niche
              </Button>
            </Stack>
          </Stack>
        </Paper>

        <Grid container spacing={2}>
          <Grid item xs={12} md={5}>
            <Paper variant="outlined" sx={{ p: 2.5, borderRadius: 3, height: "100%" }}>
              <Stack direction="row" spacing={1.25} alignItems="center" sx={{ mb: 2 }}>
                <TrendingUpIcon sx={{ color: "primary.main" }} />
                <Typography variant="h6" sx={{ fontWeight: 700 }}>
                  Creator flow
                </Typography>
              </Stack>
              <Stack spacing={1.5}>
                {steps.map((step, index) => (
                  <Stack key={step} direction="row" spacing={1.5} alignItems="flex-start">
                    <Box
                      sx={{
                        width: 28,
                        height: 28,
                        borderRadius: "50%",
                        bgcolor: "primary.main",
                        color: "#fff",
                        fontSize: "0.8rem",
                        fontWeight: 800,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        flexShrink: 0,
                      }}
                    >
                      {index + 1}
                    </Box>
                    <Typography sx={{ pt: 0.25, color: "text.secondary" }}>{step}</Typography>
                  </Stack>
                ))}
              </Stack>
            </Paper>
          </Grid>

          <Grid item xs={12} md={7}>
            <Stack spacing={2}>
              <Typography variant="h6" sx={{ fontWeight: 700 }}>
                Pick a niche lane
              </Typography>
              <Grid container spacing={2}>
                {creatorNiches.map((niche) => (
                  <Grid item xs={12} sm={6} key={niche.slug}>
                    <Card variant="outlined" sx={{ height: "100%" }}>
                      <CardContent sx={{ p: 2.25, "&:last-child": { pb: 2.25 } }}>
                        <Stack spacing={1.25}>
                          <Box
                            sx={{
                              width: 40,
                              height: 40,
                              borderRadius: 2,
                              bgcolor: `${niche.accent}18`,
                              color: niche.accent,
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontWeight: 800,
                            }}
                          >
                            {niche.label.slice(0, 1)}
                          </Box>
                          <Box>
                            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                              {niche.label}
                            </Typography>
                            <Typography variant="body2" sx={{ color: "text.secondary", mt: 0.5, lineHeight: 1.6 }}>
                              {niche.description}
                            </Typography>
                          </Box>
                          <Button
                            component={RouterLink}
                            to={`/niche/${niche.slug}`}
                            endIcon={<ArrowForwardIcon />}
                            sx={{ alignSelf: "flex-start", textTransform: "none", fontWeight: 700 }}
                          >
                            Open tab
                          </Button>
                        </Stack>
                      </CardContent>
                    </Card>
                  </Grid>
                ))}
              </Grid>
            </Stack>
          </Grid>
        </Grid>
      </Stack>
    </Box>
  )
}
