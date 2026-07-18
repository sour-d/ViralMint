import { useState } from "react"
import { Outlet, NavLink, useLocation } from "react-router-dom"
import useWebSocket from "../hooks/useWebSocket"
import {
  Box, Drawer, List, ListItemButton, ListItemIcon, ListItemText,
  Typography, Divider, IconButton, useMediaQuery, useTheme, Tooltip,
} from "@mui/material"
import CloudQueueIcon from "@mui/icons-material/CloudQueueOutlined"
import MovieCreationIcon from "@mui/icons-material/MovieCreationOutlined"
import { creatorNiches } from "../data/creatorNiches"

const DRAWER_WIDTH = 240
const COLLAPSED_WIDTH = 64

const navItems = [
  { to: "/comfyui", icon: <CloudQueueIcon />, label: "ComfyUI Setup" },
  ...creatorNiches.map((niche) => ({
    to: `/niche/${niche.slug}`,
    icon: <MovieCreationIcon />,
    label: niche.label,
  })),
]

export default function Layout() {
  useWebSocket()
  const location = useLocation()
  const theme = useTheme()
  const isNarrow = useMediaQuery(theme.breakpoints.down("md"))
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)

  const drawerWidth = collapsed && !isNarrow ? COLLAPSED_WIDTH : DRAWER_WIDTH

  const isActive = (to) => location.pathname.startsWith(to)

  const renderNavItem = ({ to, icon, label }) => {
    const active = isActive(to)
    const isCollapsed = collapsed && !isNarrow

    const button = (
      <ListItemButton
        key={to}
        component={NavLink}
        to={to}
        end={to === "/"}
        selected={active}
        sx={{
          borderRadius: 2.5,
          mb: 0.5,
          py: 0.85,
          px: isCollapsed ? 0 : 1.5,
          justifyContent: isCollapsed ? "center" : "flex-start",
          position: "relative",
          color: active ? "primary.main" : "text.secondary",
          "&.Mui-selected": {
            bgcolor: "rgba(100,149,237,0.1)",
            boxShadow: (theme) => `inset 0 0 0 1px rgba(100,149,237,0.12), ${theme.customShadows?.sm}`,
            "&:hover": { bgcolor: "rgba(100,149,237,0.13)" },
          },
          "&:hover": {
            bgcolor: "action.hover",
            color: "text.primary",
            "& .nav-icon": { transform: "scale(1.1)" },
          },
          transition: "all 0.15s ease",
        }}
      >
        <ListItemIcon
          className="nav-icon"
          sx={{
            minWidth: isCollapsed ? 0 : 34,
            color: "inherit",
            fontSize: 20,
            transition: "transform 0.15s ease",
          }}
        >
          {icon}
        </ListItemIcon>
        {!isCollapsed && (
          <ListItemText
            primary={label}
            primaryTypographyProps={{
              fontSize: "0.875rem",
              fontWeight: active ? 700 : 500,
              letterSpacing: "-0.01em",
            }}
          />
        )}
      </ListItemButton>
    )

    if (collapsed && !isNarrow) {
      return <Tooltip key={to} title={label} placement="right" arrow>{button}</Tooltip>
    }
    return button
  }

  const drawerContent = (
    <>
      <Box sx={{ px: collapsed && !isNarrow ? 1 : 2.5, py: 2.5, display: "flex", alignItems: "center", justifyContent: collapsed && !isNarrow ? "center" : "space-between" }}>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1.2, overflow: "hidden" }}>
          <Box
            component="img"
            src="/icon-192.png"
            alt="ViralMint"
            sx={{ width: 32, height: 32, borderRadius: 1, flexShrink: 0 }}
          />
          {(!collapsed || isNarrow) && (
            <Typography
              variant="h6"
              sx={{
                fontWeight: 700,
                letterSpacing: -0.5,
                fontSize: "1.15rem",
                background: "linear-gradient(135deg, #0D9F6E, #34D399)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                whiteSpace: "nowrap",
              }}
            >
              ViralMint
            </Typography>
          )}
        </Box>
        {!isNarrow && !collapsed && (
          <IconButton size="small" onClick={() => setCollapsed(true)} sx={{
            ml: 0.5, color: "primary.main", bgcolor: "action.hover",
            border: 1, borderColor: "divider",
            "&:hover": { bgcolor: "primary.main", color: "#fff" },
            transition: "all 0.15s",
          }}>
            <MovieCreationIcon sx={{ fontSize: 18 }} />
          </IconButton>
        )}
      </Box>

      <Divider sx={{ mx: collapsed && !isNarrow ? 1 : 2, mb: 1, opacity: 0.5 }} />

      <List sx={{ px: collapsed && !isNarrow ? 0.75 : 1.5, flex: 1 }}>
        {navItems.map(renderNavItem)}
      </List>
    </>
  )

  return (
    <Box sx={{ display: "flex", height: "100vh" }}>
      {isNarrow ? (
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{ "& .MuiDrawer-paper": { width: DRAWER_WIDTH } }}
        >
          {drawerContent}
        </Drawer>
      ) : (
        <Drawer
          variant="permanent"
          sx={{
            width: drawerWidth,
            flexShrink: 0,
            transition: "width 0.2s ease",
            "& .MuiDrawer-paper": {
              width: drawerWidth,
              transition: "width 0.2s ease",
              overflowX: "hidden",
            },
          }}
        >
          {drawerContent}
        </Drawer>
      )}

      <Box
        component="main"
        sx={{
          flex: 1,
          overflow: "auto",
          bgcolor: "background.default",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {isNarrow && (
          <Box sx={{
            display: "flex", alignItems: "center", gap: 1,
            px: 1.5, py: 1, flexShrink: 0,
            borderBottom: 1, borderColor: "divider",
            bgcolor: "background.paper",
          }}>
            <IconButton size="small" onClick={() => setMobileOpen(true)}>
              <MovieCreationIcon />
            </IconButton>
            <Box component="img" src="/icon-192.png" alt="" sx={{ width: 24, height: 24, borderRadius: 0.5 }} />
            <Typography
              sx={{
                fontWeight: 700, fontSize: "0.95rem",
                background: "linear-gradient(135deg, #0D9F6E, #34D399)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
              }}
            >
              ViralMint
            </Typography>
          </Box>
        )}
        <Box sx={{ flex: 1, overflow: "auto" }}>
          <Outlet />
        </Box>
      </Box>
    </Box>
  )
}
