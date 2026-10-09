/* ГРАДО 2 · сборка нового интерфейса: исходники apps/grado2/ui → apps/grado2/web/next (лежит в репозитории).
   Вызывает npm run build; имена файлов без хэшей, чтобы правка давала понятную разницу в git. Проверка: tools/ui_check.sh. */
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  base: "./",
  server: { fs: { allow: [".."] } },   // редактор листа берёт ../web/snap.js (общая привязка с рабочей страницей)
  plugins: [vue({ template: { compilerOptions: { isCustomElement: tag => tag.startsWith("wa-") } } })],
  build: {
    outDir: "../web/next",
    emptyOutDir: true,
    modulePreload: false,          // без встроенного скрипта: CSP сервера запрещает inline
    chunkSizeWarningLimit: 2000,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
});
