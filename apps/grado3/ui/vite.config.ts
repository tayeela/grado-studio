/* ГРАДО · сборка нового интерфейса (план 09.11.2026, шаг И1): apps/grado3/ui → apps/grado2/web/g3 (лежит в репозитории,
   сервер отдаёт по адресу /g3/). Имена файлов без хэшей — правка даёт понятную разницу в git; части, нужные не сразу,
   отдельными файлами (подгрузка по надобности). Проверка собранного: tools/ui_check.sh. */
import { defineConfig } from "vitest/config";
import vue from "@vitejs/plugin-vue";

export default defineConfig({
  base: "./",
  plugins: [vue({ template: { compilerOptions: { isCustomElement: tag => tag.startsWith("wa-") } } })],
  build: {
    outDir: "../../grado2/web/g3",
    emptyOutDir: true,
    modulePreload: false,          // без встроенного скрипта: CSP сервера запрещает inline
    chunkSizeWarningLimit: 1500,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
});
