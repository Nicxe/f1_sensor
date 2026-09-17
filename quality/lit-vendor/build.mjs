import { build } from 'esbuild';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

// Keep the delivered runtime versions unchanged when adding public directives.
// Author the generated asset in the HA development directory, then sync it.
const [mode, path] = process.argv.slice(2);
if (!['--check', '--write'].includes(mode) || !path) throw new Error('Usage: node build.mjs --check|--write /absolute/path/to/f1-lit-3.3.2.js');
const output = await build({
  stdin: {
    contents: "export { LitElement, html, css, svg } from 'lit'; export { repeat } from 'lit/directives/repeat.js';",
    resolveDir: fileURLToPath(new URL('.', import.meta.url)),
    sourcefile: 'f1-lit-entry.js',
  },
  bundle: true, minify: true, format: 'esm', platform: 'browser', target: 'es2020',
  // Escaped string literals keep significant whitespace out of line endings.
  supported: { 'template-literal': false },
  legalComments: 'eof', write: false,
});
const bytes = output.outputFiles[0].contents;
if (mode === '--write') await writeFile(path, bytes);
else if (!Buffer.from(bytes).equals(await readFile(path))) throw new Error('Vendored Lit differs from the pinned build');
console.log(`Vendored Lit ${mode === '--write' ? 'written' : 'verified'} (${bytes.length} bytes)`);
