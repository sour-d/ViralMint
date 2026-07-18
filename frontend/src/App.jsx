import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom"
import { Snackbar, Alert, Button, CircularProgress, Box } from "@mui/material"
import ErrorBoundary from "./components/ErrorBoundary"
import Layout from "./components/Layout"
import useAppStore from "./store/appStore"
import { pluginRoutes } from "./plugins"
import CreatorNiche from "./pages/CreatorNiche"

const ComfyUISetup = lazy(() => import("./pages/ComfyUISetup"))
const AnimeLofiStudio = lazy(() => import("./pages/AnimeLofiStudio"))

const LazyFallback = () => (
  <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100%", minHeight: 200 }}>
    <CircularProgress size={36} />
  </Box>
)

function GlobalSnackbar() {
  const snackbar = useAppStore((s) => s.snackbar)
  const closeSnackbar = useAppStore((s) => s.closeSnackbar)
  const navigate = useNavigate()

  return (
    <Snackbar
      open={snackbar.open}
      autoHideDuration={snackbar.action ? 6000 : 4000}
      onClose={closeSnackbar}
      anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
    >
      <Alert
        onClose={closeSnackbar}
        severity={snackbar.severity}
        variant="filled"
        sx={{ width: "100%", borderRadius: 2, alignItems: "center" }}
        action={snackbar.action ? (
          <Button
            color="inherit"
            size="small"
            sx={{ fontWeight: 700, whiteSpace: "nowrap" }}
            onClick={() => { navigate(snackbar.action.href); closeSnackbar() }}
          >
            {snackbar.action.label}
          </Button>
        ) : undefined}
      >
        {snackbar.message}
      </Alert>
    </Snackbar>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <ErrorBoundary>
        <Suspense fallback={<LazyFallback />}>
          <Routes>
            <Route path="/" element={<Layout />}>
              <Route index element={<Navigate to="/niche/anime-lofi" />} />
              <Route path="niche/:slug" element={<CreatorNiche />} />
              <Route path="comfyui" element={<ComfyUISetup />} />
              <Route path="anime-lofi" element={<AnimeLofiStudio />} />
              {pluginRoutes.map(({ path, element }) => (
                <Route key={path} path={path} element={element} />
              ))}
              <Route path="*" element={<Navigate to="/niche/anime-lofi" />} />
            </Route>
          </Routes>
        </Suspense>
        <GlobalSnackbar />
      </ErrorBoundary>
    </BrowserRouter>
  )
}
