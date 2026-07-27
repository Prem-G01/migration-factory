export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        void: '#080B0F',
        surface: '#0D1117',
        raised: '#161B22',
        border: '#21262D',
        cyan: { DEFAULT: '#00E5FF', 10: '#00E5FF1A', 30: '#00E5FF4D' },
        orange: { DEFAULT: '#FF6B35', 10: '#FF6B351A' },
        green: { DEFAULT: '#39D353', 10: '#39D3531A', 20: '#39D35333' },
        red: { DEFAULT: '#F85149', 10: '#F851491A' },
        yellow: { DEFAULT: '#E3B341', 10: '#E3B3411A' },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      animation: {
        'fade-up': 'fade-up 0.4s ease forwards',
        'pulse-slow': 'pulse 3s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
