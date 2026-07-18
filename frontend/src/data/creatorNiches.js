export const creatorNiches = [
  {
    slug: "money-shorts",
    label: "Money Shorts",
    description: "Fast finance, business, and making-money ideas with a sharp hook.",
    promptSeed: "Write a punchy vertical short about a money or business idea. Open with a bold hook, keep the pace fast, and end with one actionable takeaway.",
    accent: "#0d9f6e",
  },
  {
    slug: "ai-tools",
    label: "AI Tools",
    description: "Demo AI apps, workflows, and creator hacks that feel useful in under 60 seconds.",
    promptSeed: "Write a short-form video about an AI tool or workflow. Start with a transformation hook, show the value quickly, and keep every line tight.",
    accent: "#2563eb",
  },
  {
    slug: "pop-culture",
    label: "Pop Culture",
    description: "Commentary, reaction, and entertainment clips built for shares and conversation.",
    promptSeed: "Write a high-energy entertainment short about a trending topic. Lead with a strong opinion, use quick beats, and finish with a conversation starter.",
    accent: "#dc2626",
  },
  {
    slug: "niche1",
    label: "Quote Shorts",
    description: "Emotional quote shorts with a podcast-style talking head. Image → Script → Lip-sync → Captions + Music.",
    promptSeed: "Write a short emotional monologue about self-love, relationships, or personal growth. Warm, intimate, and uplifting.",
    accent: "#c96442",
  },
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
