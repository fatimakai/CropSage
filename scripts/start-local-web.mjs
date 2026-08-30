import { spawn } from "node:child_process";

import { getLocalSupabaseCredentials } from "./import-usda-csb.mjs";

const credentials = getLocalSupabaseCredentials();
const npmEntryPoint = process.env.npm_execpath;
if (!npmEntryPoint) throw new Error("Run this launcher through npm run web:dev:local.");

const child = spawn(process.execPath, [npmEntryPoint, "run", "web:dev"], {
  env: {
    ...process.env,
    NEXT_PUBLIC_SUPABASE_URL: credentials.supabaseUrl,
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: credentials.publishableKey,
    SUPABASE_SECRET_KEY: credentials.secretKey,
  },
  stdio: "inherit",
});

child.on("exit", (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exitCode = code ?? 1;
});
