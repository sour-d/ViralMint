import { lazy, Suspense } from "react"
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from "react-router-dom"
import { Snackbar, Alert, Button, CircularProgress, Box } from "@mui/material"
import ErrorBoundary from "./components/ErrorBoundary"
import Layout from "./components/Layout"
import useAppStore from "./store/appStore"
import { pluginRoutes } from "./plugins"

// Route-level code splitting — only Chat is eagerly loaded (home page)
import Chat from "./pages/Chat"
const Settings = lazy(() => import("./pages/Settings"))
const Videos = lazy(() => import("./pages/Videos"))
const StockVideo = lazy(() => import("./pages/StockVideo"))
const Channels = lazy(() => import("./pages/Channels"))
const Messaging = lazy(() => import("./pages/Messaging"))
const ClipStudio = lazy(() => import("./pages/ClipStudio"))
const AiVideo = lazy(() => import("./pages/AiVideo"))

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
              <Route index element={<Chat />} />
              <Route path="dashboard" element={<Navigate to="/videos" />} />
              <Route path="videos" element={<Videos />} />
              <Route path="stock" element={<StockVideo />} />
              <Route path="ai-video" element={<AiVideo />} />
              <Route path="avatar" element={<Navigate to="/stock" />} />
              <Route path="create" element={<Navigate to="/stock" />} />
              <Route path="cron" element={<Navigate to="/" />} />
              <Route path="clips" element={<ClipStudio />} />
              <Route path="channels" element={<Channels />} />
              <Route path="messaging" element={<Messaging />} />
              <Route path="settings" element={<Settings />} />
              {pluginRoutes.map(({ path, element }) => (
                <Route key={path} path={path} element={element} />
              ))}
              <Route path="*" element={<Navigate to="/" />} />
            </Route>
          </Routes>
        </Suspense>
        <GlobalSnackbar />
      </ErrorBoundary>
    </BrowserRouter>
  )
}
