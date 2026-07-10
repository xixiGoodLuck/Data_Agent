/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#17201f",
        canvas: "#f5f7f6",
        teal: {
          50: "#eefbf8",
          100: "#d7f5ee",
          500: "#16977f",
          600: "#0d7968",
          700: "#0b6155"
        }
      },
      boxShadow: {
        panel: "0 1px 2px rgba(23, 32, 31, 0.06), 0 8px 24px rgba(23, 32, 31, 0.04)"
      }
    }
  },
  plugins: []
};
