import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// `npm run dev` serves the desk at http://localhost:5173 and opens the browser.
// The page calls the FastAPI backend directly at http://localhost:8000
// (see src/api.ts); the backend allows this origin via CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    open: true,
  },
});
