import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#000",
        fg: "#fff",
        dim: "#6b6b6b",
        accent: "#00ff9c",
        accentBg: "#001b10",
        border: "#222",
        muted: "#0e0e0e",
      },
      fontFamily: {
        sans: [
          "Pretendard",
          "Apple SD Gothic Neo",
          "Malgun Gothic",
          "sans-serif",
        ],
      },
      fontSize: {
        // 시안: clamp(64px, 12vw, 180px) 등 — 직접 inline 으로 처리
      },
      letterSpacing: {
        tighter2: "-0.04em",
        tightest: "-0.05em",
      },
    },
  },
  plugins: [],
};

export default config;
