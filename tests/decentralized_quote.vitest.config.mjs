import { defineConfig } from "../landing/node_modules/vite/dist/node/index.js";
import react from "../landing/node_modules/@vitejs/plugin-react/dist/index.js";
import { fileURLToPath } from "node:url";

export default defineConfig({
  root: fileURLToPath(new URL("../landing/", import.meta.url)),
  plugins: [react()],
  resolve: { dedupe: ["react", "react-dom"], alias: {
    react: fileURLToPath(new URL("../landing/node_modules/react", import.meta.url)),
    "react-dom": fileURLToPath(new URL("../landing/node_modules/react-dom", import.meta.url)),
  } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./tests/setup.js"],
    include: ["../tests/decentralized_quote_frontend.test.jsx"],
    env: { VITE_API_URL: "", VITE_CHAT_URL: "" },
  },
});
