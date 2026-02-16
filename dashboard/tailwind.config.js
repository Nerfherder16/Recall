import defaultTheme from "tailwindcss/defaultTheme";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", ...defaultTheme.fontFamily.sans],
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        "recall-dark": {
          primary: "#a78bfa",
          "primary-content": "#0f0e17",
          secondary: "#60a5fa",
          "secondary-content": "#0f172a",
          accent: "#34d399",
          "accent-content": "#052e16",
          neutral: "#1e1e24",
          "neutral-content": "#a1a1aa",
          "base-100": "#1a1a20",
          "base-200": "#141418",
          "base-300": "#111114",
          "base-content": "#e4e4e7",
          info: "#7dd3fc",
          "info-content": "#082f49",
          success: "#4ade80",
          "success-content": "#052e16",
          warning: "#fbbf24",
          "warning-content": "#422006",
          error: "#f87171",
          "error-content": "#450a0a",
        },
      },
      {
        "recall-light": {
          primary: "#7c3aed",
          "primary-content": "#ffffff",
          secondary: "#3b82f6",
          "secondary-content": "#ffffff",
          accent: "#059669",
          "accent-content": "#ffffff",
          neutral: "#e4e4e7",
          "neutral-content": "#27272a",
          "base-100": "#ffffff",
          "base-200": "#f8f8fa",
          "base-300": "#f0f0f3",
          "base-content": "#1a1a20",
          info: "#0ea5e9",
          "info-content": "#ffffff",
          success: "#16a34a",
          "success-content": "#ffffff",
          warning: "#d97706",
          "warning-content": "#ffffff",
          error: "#dc2626",
          "error-content": "#ffffff",
        },
      },
    ],
  },
};
