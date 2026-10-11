/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#fff8ed",
          100: "#ffefd3",
          200: "#fedca5",
          300: "#fdc26d",
          400: "#fb9d32",
          500: "#f9820a",
          600: "#e66600",
          700: "#bf4c02",
          800: "#983c09",
          900: "#7b320b",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(15, 23, 42, 0.04), 0 1px 3px rgba(15, 23, 42, 0.06)",
        float: "0 12px 40px rgba(15, 23, 42, 0.18)",
      },
    },
  },
  plugins: [],
};
