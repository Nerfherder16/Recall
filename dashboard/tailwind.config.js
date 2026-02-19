import defaultTheme from "tailwindcss/defaultTheme";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        display: ["Clash Display", ...defaultTheme.fontFamily.sans],
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
        mono: ["JetBrains Mono", ...defaultTheme.fontFamily.mono],
      },
      colors: {
        surface: {
          primary: "var(--surface-primary)",
          card: "var(--surface-card)",
          elevated: "var(--surface-elevated)",
        },
        content: {
          primary: "var(--content-primary)",
          secondary: "var(--content-secondary)",
          muted: "var(--content-muted)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          muted: "var(--accent-muted)",
        },
        border: {
          surface: "var(--border-surface)",
        },
      },
      boxShadow: {
        glow: "0 0 20px var(--glow-color, rgba(139, 92, 246, 0.15))",
        "glow-sm": "0 0 10px var(--glow-color, rgba(139, 92, 246, 0.1))",
        "glow-lg": "0 0 40px var(--glow-color, rgba(139, 92, 246, 0.2))",
        "glow-accent": "0 0 20px rgba(139, 92, 246, 0.25)",
        "glow-success": "0 0 20px rgba(16, 185, 129, 0.2)",
        "glow-error": "0 0 20px rgba(239, 68, 68, 0.2)",
      },
      animation: {
        shimmer: "shimmer 2s linear infinite",
      },
      keyframes: {
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};
