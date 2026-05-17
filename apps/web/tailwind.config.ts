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
                // Rico AI Cinematic Design System
                background: "#131313",
                surface: "#131313",
                "surface-dim": "#131313",
                "surface-bright": "#3a3939",
                "surface-container": "#201f1f",
                "surface-container-low": "#1c1b1b",
                "surface-container-lowest": "#0e0e0e",
                "surface-container-high": "#2a2a2a",
                "surface-container-highest": "#353535",
                "surface-variant": "#353534",
                "surface-tint": "#00dddd",

                on: {
                    background: "#e5e2e1",
                    surface: "#e5e2e1",
                    "surface-variant": "#b9cac9",
                    primary: "#003737",
                    "primary-container": "#007070",
                    secondary: "#5b005b",
                    "secondary-container": "#500050",
                    tertiary: "#383100",
                    "tertiary-container": "#716500",
                    error: "#690005",
                    "error-container": "#ffdad6",
                },

                primary: "#ffffff",
                "primary-fixed": "#00fbfb",
                "primary-fixed-dim": "#00dddd",
                "on-primary-fixed": "#002020",
                "on-primary-fixed-variant": "#004f4f",
                "inverse-primary": "#006a6a",

                secondary: "#ffabf3",
                "secondary-fixed": "#ffd7f5",
                "secondary-fixed-dim": "#ffabf3",
                "on-secondary-fixed": "#380038",
                "on-secondary-fixed-variant": "#810081",

                tertiary: "#ffffff",
                "tertiary-fixed": "#fce442",
                "tertiary-fixed-dim": "#dec723",
                "on-tertiary-fixed": "#201c00",
                "on-tertiary-fixed-variant": "#504700",

                error: "#ffb4ab",
                "error-container": "#93000a",

                outline: "#839493",
                "outline-variant": "#3a4a49",

                "inverse-surface": "#e5e2e1",
                "inverse-on-surface": "#313030",

                // Surface glass for glassmorphism
                "surface-glass": "rgba(255, 255, 255, 0.03)",

                // Glow effects
                "glow-cyan": "rgba(0, 229, 255, 0.12)",
                "glow-magenta": "rgba(255, 45, 142, 0.18)",
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
                display: ["var(--font-sora)", "sans-serif"],
                headline: ["var(--font-sora)", "sans-serif"],
                body: ["var(--font-inter)", "sans-serif"],
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
