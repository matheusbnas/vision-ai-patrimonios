/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        cor: {
          blue: '#1e3a5f',
          'blue-light': '#2d5f8a',
          gold: '#c9a84c',
          'gold-light': '#e8d48b',
          red: '#dc2626',
          green: '#16a34a',
          dark: '#0f172a',
          gray: '#334155',
        },
      },
    },
  },
  plugins: [],
}
