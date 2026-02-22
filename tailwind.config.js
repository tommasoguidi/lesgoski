/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: [
    "./src/lesgoski/webapp/templates/**/*.html",
    "./src/lesgoski/webapp/static/*.js",
  ],
  theme: {
    extend: {
      colors: {
        primary: "#3b82f6",
        "background-light": "#f8fafc",
        "background-dark": "#0f172a",
        "card-dark": "#1e293b",
        "accent-green": "#22c55e",
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "12px",
      },
    },
  },
  plugins: [
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/container-queries"),
  ],
};
