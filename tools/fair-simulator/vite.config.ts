import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  server: {
    open: true, // auto-open browser
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});