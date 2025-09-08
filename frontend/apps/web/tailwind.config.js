/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: false,
  content: ["./index.html", "./src/**/*.{ts,tsx,js,jsx}"],
  theme: {
    extend: {},
  },
  plugins: [require("@tailwindcss/typography")],
}
