import type { Config } from "tailwindcss";

const config: Config = {
    darkMode: "class",
    content: [
        "./app/**/*.{ts,tsx}",
        "./components/**/*.{ts,tsx}",
        "./lib/**/*.{ts,tsx}",
    ],
    theme: {
        extend: {
            colors: {
                // Rico AI Cinematic Design System v2
                // Based on DESIGN.md spec: pure black + magenta + cyan

                // Global Canvas - Pure Black
                background: "#000000",
                surface: {
                    DEFAULT: "#0a0a0f",
                    elevated: "#111116",
                    subtle: "rgba(255, 255, 255, 0.02)",
                    glass: "rgba(255, 255, 255, 0.04)",
                },

                // Primary System - Magenta
                magenta: {
                    DEFAULT: "#ff2d8e",
                    glow: "rgba(255, 45, 142, 0.3)",
                    soft: "rgba(255, 45, 142, 0.1)",
                    dim: "rgba(255, 45, 142, 0.05)",
                    hover: "#ff4a9e",
                },

                // Secondary System - Cyan
                cyan: {
                    DEFAULT: "#00e5ff",
                    glow: "rgba(0, 229, 255, 0.3)",
                    soft: "rgba(0, 229, 255, 0.1)",
                    dim: "rgba(0, 229, 255, 0.05)",
                    hover: "#33ebff",
                },

                // Gradient System
                gradient: {
                    magenta: "linear-gradient(135deg, #ff2d8e 0%, #ff1a5c 100%)",
                    cyan: "linear-gradient(135deg, #00e5ff 0%, #00b8cc 100%)",
                    duo: "linear-gradient(135deg, #ff2d8e 0%, #00e5ff 100%)",
                    subtle: "linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%)",
                },

                // Text System - High Contrast White + Grayscale
                text: {
                    primary: "#ffffff",
                    secondary: "rgba(255, 255, 255, 0.72)",
                    tertiary: "rgba(255, 255, 255, 0.48)",
                    muted: "rgba(255, 255, 255, 0.28)",
                    disabled: "rgba(255, 255, 255, 0.16)",
                },

                // Border System
                border: {
                    subtle: "rgba(255, 255, 255, 0.06)",
                    soft: "rgba(255, 255, 255, 0.1)",
                    medium: "rgba(255, 255, 255, 0.16)",
                    strong: "rgba(255, 255, 255, 0.24)",
                    gradient: "linear-gradient(135deg, rgba(255,45,142,0.5) 0%, rgba(0,229,255,0.5) 100%)",
                },

                // Legacy compatibility layer (transition period)
                // These map to new system for backward compatibility
                "surface-container": "#0a0a0f",
                "surface-variant": "#111116",
                primary: "#ffffff",
                secondary: "#00e5ff",
                error: "#ff5e5b",
                outline: "rgba(255, 255, 255, 0.1)",
                rico: {
                    bg: "#000000",
                    surface: "#0a0a0f",
                    "surface-2": "#111116",
                    border: "rgba(255, 255, 255, 0.06)",
                    accent: "#ff2d8e",
                    "accent-hover": "#ff4a9e",
                    "accent-muted": "rgba(255, 45, 142, 0.1)",
                    "accent-border": "rgba(255, 45, 142, 0.4)",
                    "accent-glow": "rgba(255, 45, 142, 0.2)",
                    text: "#ffffff",
                    "text-muted": "rgba(255, 255, 255, 0.72)",
                    "text-dim": "rgba(255, 255, 255, 0.48)",
                    purple: "#ff2d8e",
                    teal: "#00e5ff",
                    red: "#ff5e5b",
                    amber: "#f5a623",
                },
            },
            borderRadius: {
                DEFAULT: "0.25rem",
                lg: "0.5rem",
                xl: "0.75rem",
                full: "9999px",
            },
            spacing: {
                unit: "8px",
                gutter: "32px",
                "section-gap": "128px",
                "container-max": "1440px",
                "safe-area": "48px",
                "container-padding-mobile": "24px",
                "container-padding-desktop": "120px",
            },
            fontFamily: {
                // DESIGN.md spec: IBM Plex Sans Variable + Sora
                display: ["var(--font-ibm-plex-sans)", "var(--font-sora)", "sans-serif"],
                headline: ["var(--font-ibm-plex-sans)", "var(--font-sora)", "sans-serif"],
                body: ["var(--font-ibm-plex-sans)", "system-ui", "sans-serif"],
                mono: ["var(--font-space-mono)", "monospace"],
            },
            fontSize: {
                "display-lg": ["80px", { lineHeight: "1.1", letterSpacing: "-0.04em", fontWeight: "700" }],
                "display-lg-mobile": ["48px", { lineHeight: "1.1", letterSpacing: "-0.02em", fontWeight: "700" }],
                "headline-xl": ["48px", { lineHeight: "1.2", letterSpacing: "-0.02em", fontWeight: "600" }],
                "headline-lg": ["32px", { lineHeight: "1.3", fontWeight: "500" }],
                "headline-md": ["32px", { lineHeight: "1.3", fontWeight: "500" }],
                "body-lg": ["18px", { lineHeight: "1.6", letterSpacing: "0.02em", fontWeight: "300" }],
                "body-md": ["16px", { lineHeight: "1.6", letterSpacing: "0.01em", fontWeight: "300" }],
                "label-caps": ["12px", { lineHeight: "1.0", letterSpacing: "0.15em", fontWeight: "400" }],
            },
            animation: {
                float: "float 14s ease-in-out infinite",
                "float-delayed": "float 16s ease-in-out infinite -4s",
                "pulse-magenta": "pulse-magenta 10s ease-in-out infinite",
                "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
                thinking: "thinking 3s ease-in-out infinite",
            },
            keyframes: {
                float: {
                    "0%, 100%": { transform: "translateY(0px) rotate(0deg)" },
                    "50%": { transform: "translateY(-30px) rotate(0.8deg)" },
                },
                "pulse-magenta": {
                    "0%, 100%": { opacity: "0.3", filter: "blur(140px)" },
                    "50%": { opacity: "0.7", filter: "blur(180px)" },
                },
                thinking: {
                    "0%, 100%": { opacity: "0.15", transform: "scale(1)" },
                    "50%": { opacity: "0.25", transform: "scale(1.05)" },
                },
            },
            backdropBlur: {
                xs: "2px",
            },
        },
    },
    plugins: [],
};

export default config;
