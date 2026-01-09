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

function detectNewline(text) {
  return text.includes("\r\n") ? "\r\n" : "\n";
}

function upsertVersionPreservingFormat(text, version) {
  // 1) If the key exists, replace only the string value.
  //    Keep whitespace around ":" exactly as-is.
  const existing = /("version"\s*:\s*")([^"]*)(")/m;
  if (existing.test(text)) {
    return text.replace(existing, `$1${version}$3`);
  }

  // 2) If the key doesn't exist, insert it as the last top-level property.
  //    We try hard to preserve the file's current formatting (single-line vs multi-line,
  //    indentation, newline style) and only touch what's needed.
  const newline = detectNewline(text);
  const isMultiline = text.includes("\n");

  if (!isMultiline) {
    // Single-line JSON object: insert before final "}"
    const lastBrace = text.lastIndexOf("}");
    if (lastBrace === -1) return text;

    const beforeBrace = text.slice(0, lastBrace);
    const afterBrace = text.slice(lastBrace); // includes "}" and any trailing whitespace

    // Determine whether object is empty (only "{" + whitespace)
    const openBrace = beforeBrace.indexOf("{");
    const inside = openBrace === -1 ? "" : beforeBrace.slice(openBrace + 1).trim();
    const needsComma = inside.length > 0 && !inside.endsWith(",");

    const insertion = `${needsComma ? "," : ""} "version": "${version}"`;
    return `${beforeBrace}${insertion}${afterBrace}`;
  }

  // Multi-line JSON: insert a new line before the closing "}" and ensure
  // the previous property has a trailing comma.
  const lines = text.split(/\r?\n/);

  // Find the closing brace line (ignoring trailing blank lines).
  let closeIdx = lines.length - 1;
  while (closeIdx > 0 && lines[closeIdx].trim() === "") closeIdx -= 1;
  if (lines[closeIdx].trim() !== "}") {
    // Fall back to returning original text if we can't confidently insert.
    return text;
  }

  // Indentation: reuse the indentation of the first property line if possible.
  const indentMatch = text.match(/^[ \t]+(?="[^"]+"\s*:)/m);
  const indent = indentMatch ? indentMatch[0] : "  ";

  // Find the last property line before "}".
  let propIdx = closeIdx - 1;
  while (propIdx >= 0 && !/:\s*/.test(lines[propIdx])) propIdx -= 1;

  if (propIdx >= 0 && !lines[propIdx].trim().endsWith(",")) {
    lines[propIdx] = `${lines[propIdx].replace(/\s*$/, "")},`;
  }

  lines.splice(closeIdx, 0, `${indent}"version": "${version}"`);
  return lines.join(newline);
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const file = args.file;
  const versionRaw = args.version;

  if (!file || !versionRaw) {
    // eslint-disable-next-line no-console
    console.error(
      "Usage: node .release/update-manifest-version.js --file <path> --version <version>"
    );
    process.exit(2);
  }

  // Keep semantic-release version as-is (including prereleases), but normalize the prerelease
  // tag casing to match the project's manifest convention (e.g. "beta" -> "Beta").
  // Example: "3.0.0-beta.7" -> "3.0.0-Beta.7"
  const version = String(versionRaw).replace(/-(\w)/, (_, c) => `-${String(c).toUpperCase()}`);

  if (!fs.existsSync(file)) {
    throw new Error(`File not found: ${file}`);
  }

  const before = fs.readFileSync(file, "utf8");
  let beforeVersion;
  try {
    beforeVersion = JSON.parse(before)?.version;
  } catch (e) {
    beforeVersion = undefined;
  }

  const after = upsertVersionPreservingFormat(before, version);

  // If we still haven't changed anything, something is off (e.g., unexpected structure).
  if (after === before) {
    // If the manifest already has the desired version, that's fine (idempotent).
    let parsed;
    try {
      parsed = JSON.parse(before);
    } catch (e) {
      throw new Error(
        `Could not update or insert "version" field in ${file} (unexpected format)`
      );
    }
    if (String(parsed?.version ?? "") === String(version)) {
      return;
    }
    throw new Error(
      `Could not update or insert "version" field in ${file} (unexpected format)`
    );
  }

  // Validate we didn't break JSON.
  JSON.parse(after);

  fs.writeFileSync(file, after);

  // Log what we actually wrote, so Actions output is unambiguous.
  let writtenVersion;
  try {
    writtenVersion = JSON.parse(fs.readFileSync(file, "utf8"))?.version;
  } catch (e) {
    writtenVersion = undefined;
  }
  // eslint-disable-next-line no-console
  console.log(
    `[update-manifest-version] ${file}: ${String(beforeVersion ?? "")} -> ${String(
      versionRaw
    )} (written: ${String(writtenVersion ?? "")})`
  );
}

main();

