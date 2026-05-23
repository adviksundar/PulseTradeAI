import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14171f",
        panel: "#f7f8fb",
        line: "#dfe3eb",
        gain: "#087f5b",
        loss: "#c92a2a",
        signal: "#2454d6"
      }
    }
  },
  plugins: []
} satisfies Config;

