export const creatorNiches = [
  {
    slug: "anime-lofi",
    label: "anime-lofi",
    description: "Script → Audio → Image-per-segment → Raw video. Cinematic storytelling with a unique image per 3-4 second clip.",
    promptSeed: "Write a vivid descriptive script that creates distinct visual scenes, each sentence evoking a different image.",
    accent: "#6495ed",
  },
]

export const creatorRoutes = [
  { to: "/creator", label: "Creator Home", description: "Overview and shortcuts" },
  { to: "/comfyui", label: "ComfyUI Setup", description: "Pod, workflow, models" },
  ...creatorNiches.map((niche) => ({
    to: `/niche/${niche.slug}`,
    label: niche.label,
    description: niche.description,
  })),
]
