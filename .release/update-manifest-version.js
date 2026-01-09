const fs = require("fs");

function parseArgs(argv) {
  const out = {};
  for (let i = 0; i < argv.length; i += 1) {
    const a = argv[i];
    if (!a.startsWith("--")) continue;
    const key = a.slice(2);
    const value = argv[i + 1];
    out[key] = value;
    i += 1;
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const file = args.file;
  const version = args.version;

  if (!file || !version) {
    // eslint-disable-next-line no-console
    console.error(
      "Usage: node .release/update-manifest-version.js --file <path> --version <version>"
    );
    process.exit(2);
  }

  const before = fs.readFileSync(file, "utf8");

  // Replace only the value, preserving original whitespace/formatting.
  const re = /("version"\s*:\s*")([^"]*)(")/;
  const after = before.replace(re, `$1${version}$3`);

  if (after === before) {
    throw new Error(`Could not find "version" field in ${file}`);
  }

  // Validate we didn't break JSON.
  JSON.parse(after);

  fs.writeFileSync(file, after);
}

main();

