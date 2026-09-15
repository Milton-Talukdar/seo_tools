import { defineConfig } from 'astro/config';

export default defineConfig({
  output: 'static',
  srcDir: 'src',
  publicDir: 'public',
  outDir: 'dist',
  trailingSlash: 'never',
});
