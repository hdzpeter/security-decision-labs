/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_FAIR_API_URL: string;
  readonly VITE_BENCHMARK_API_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}