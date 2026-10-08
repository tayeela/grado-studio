/* ГРАДО 2 · сборка нового интерфейса (Vite + Vue 3): `npm run dev` — пробная страница редактора листа на :5173,
   `npm run build` — файлы в dist/ (в репозиторий не кладутся). Разрешает читать ../web: редактор берёт оттуда snap.js. */
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  plugins: [vue()],
  base: "./",
  server: { port: 5173, strictPort: false, fs: { allow: [".."] } },
  build: { outDir: "dist", emptyOutDir: true },
});
