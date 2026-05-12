import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        rico: {
          bg: "#06060f",
          surface: {
            DEFAULT: "#0e0e20",
            1: "#0e0e20",
            2: "#13132a",
            3: "#1a1a33",
          },
          accent: {
            DEFAULT: "#5b4fff",
            hover: "#4a3fe0",
            glow: "rgba(91,79,255,0.28)",
            muted: "rgba(91,79,255,0.12)",
            border: "rgba(91,79,255,0.18)",
          },
          purple: "#a78bfa",
          teal: {
            DEFAULT: "#00c9a7",
            muted: "rgba(0,201,167,0.08)",
          },
          amber: {
            DEFAULT: "#f5a623",
            muted: "rgba(245,166,35,0.08)",
          },
          red: {
            DEFAULT: "#ff5e5b",
            muted: "rgba(255,94,91,0.08)",
          },
          text: {
            DEFAULT: "#eeeef5",
            muted: "#8080a0",
            dim: "#5a5a7a",
          },
          border: {
            DEFAULT: "rgba(255,255,255,0.06)",
            hover: "rgba(255,255,255,0.1)",
          },
        },
      },
      fontFamily: {
        display: ["'Cabinet Grotesk'", "sans-serif"],
        body: ["'Instrument Sans'", "sans-serif"],
        mono: ["'JetBrains Mono'", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
