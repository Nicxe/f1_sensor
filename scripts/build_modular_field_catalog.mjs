import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

import {
  FIELDS,
  MODULES,
  VERSION,
  fieldDefinition,
  moduleFields,
} from '../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const JSON_PATH = path.join(ROOT, 'quality', 'modular-field-catalog.json');
const MARKDOWN_PATH = path.join(ROOT, 'quality', 'modular-field-catalog.md');
const AFFECTING_OPTIONS = new Set(['content', 'competitors']);

const clone = value => JSON.parse(JSON.stringify(value));
const compare = (left, right) => left.localeCompare(right, 'en');

function moduleVariants(definition) {
  const dimensions = Object.entries(definition.options ?? {})
    .filter(([name, option]) => AFFECTING_OPTIONS.has(name) && option.type === 'enum')
    .map(([name, option]) => [name, option.values]);
  if (!dimensions.length) return [{ id: 'default', options: {} }];
  return dimensions.reduce(
    (variants, [name, values]) => variants.flatMap(variant => values.map(value => ({
      id: [...(variant.id === 'default' ? [] : [variant.id]), `${name}=${value}`].join(','),
      options: { ...variant.options, [name]: value },
    }))),
    [{ id: 'default', options: {} }],
  );
}

function normalizeField(field) {
  const required = ['id', 'label', 'source', 'path', 'type', 'capability', 'modes', 'sessions', 'identity', 'generation', 'timestamps', 'freshness', 'presentations'];
  for (const key of required) {
    if (field?.[key] === undefined || field[key] === null || field[key] === '') {
      throw new Error(`Field ${field?.id ?? '<unknown>'} is missing ${key}`);
    }
  }
  return Object.fromEntries(Object.entries(clone(field)).sort(([left], [right]) => compare(left, right)));
}

export function buildCatalog() {
  const modules = Object.values(MODULES).sort((left, right) => compare(left.id, right.id)).map(definition => ({
    id: definition.id,
    label: clone(definition.label),
    sources: [...definition.sources].sort(compare),
    variants: moduleVariants(definition).map(variant => {
      const module = { type: definition.id, options: { ...Object.fromEntries(Object.entries(definition.options ?? {}).map(([name, option]) => [name, clone(option.default)])), ...variant.options } };
      const fields = moduleFields(module).map(id => {
        const field = fieldDefinition(module, id);
        if (!field) throw new Error(`${definition.id}/${variant.id} references unknown field ${id}`);
        return normalizeField(field);
      });
      return { id: variant.id, options: variant.options, fields };
    }),
  }));
  const used = new Set(modules.flatMap(module => module.variants.flatMap(variant => variant.fields.map(field => field.id))));
  const unused = Object.keys(FIELDS).filter(id => !used.has(id)).sort(compare);
  if (unused.length) throw new Error(`Fields are not exposed by any module variant: ${unused.join(', ')}`);
  const sources = [...new Set(modules.flatMap(module => module.variants.flatMap(variant => variant.fields.map(field => field.source))))].sort(compare);
  return {
    format_version: 1,
    configuration_version: VERSION,
    generated_from: 'modular/catalog.js',
    field_count: Object.keys(FIELDS).length,
    module_count: modules.length,
    sources,
    modules,
  };
}

const list = values => Array.isArray(values) ? values.join(', ') : String(values ?? '');
const timestampText = timestamps => Object.entries(timestamps).map(([kind, value]) => `${kind}: ${value}`).join('; ');
const escapeCell = value => String(value ?? '').replaceAll('|', '\\|').replaceAll('\n', ' ');

export function renderMarkdown(catalog) {
  const lines = [
    '# Modular F1 card field catalog',
    '',
    'This catalog is generated from the delivered module registry. It records the source path, data capability, supported modes and sessions, identity boundary, time provenance, freshness rule, unit and presentation for every field in every content-dependent module variant.',
    '',
    `Configuration version: ${catalog.configuration_version}. Modules: ${catalog.module_count}. Base field IDs: ${catalog.field_count}. Resolved sources: ${catalog.sources.length}.`,
    '',
    'A source path describes the contract consumed by the card; it is not a promise that the value is available in every session. `identity` lists the values that must still describe the same observation before fields may be combined. `timestamps` distinguishes source time, receipt time, entity update time and display snapshot time where the source supplies them.',
    '',
  ];
  for (const module of catalog.modules) {
    lines.push(`## ${module.label.en} (\`${module.id}\`)`, '', `Declared sources: ${module.sources.map(source => `\`${source}\``).join(', ')}.`, '');
    for (const variant of module.variants) {
      if (module.variants.length > 1) lines.push(`### ${variant.id}`, '');
      lines.push('| Field | Source and path | Coverage | Identity and time | Presentation |', '| --- | --- | --- | --- | --- |');
      for (const field of variant.fields) {
        const source = `\`${field.source}\` → \`${field.path}\``;
        const coverage = `Capability: ${field.capability}; modes: ${list(field.modes)}; sessions: ${list(field.sessions)}; freshness: ${field.freshness}${field.spoiler ? '; spoiler-protected' : ''}${field.estimated ? '; estimated/derived' : ''}`;
        const identity = `Identity: ${list(field.identity)}; generation: ${field.generation}; time: ${timestampText(field.timestamps)}`;
        const presentation = `Type: ${field.type}${field.unit ? `; unit: ${field.unit}` : ''}; ${list(field.presentations)}`;
        lines.push(`| \`${field.id}\` — ${escapeCell(field.label.en)} / ${escapeCell(field.label.sv)} | ${escapeCell(source)} | ${escapeCell(coverage)} | ${escapeCell(identity)} | ${escapeCell(presentation)} |`);
      }
      lines.push('');
    }
  }
  return `${lines.join('\n').trimEnd()}\n`;
}

export function serializeCatalog(catalog) {
  return `${JSON.stringify(catalog, null, 2)}\n`;
}

async function checkFile(file, expected) {
  let actual;
  try { actual = await readFile(file, 'utf8'); } catch { throw new Error(`${path.relative(ROOT, file)} is missing; run this script with --write`); }
  if (actual !== expected) throw new Error(`${path.relative(ROOT, file)} is stale; run this script with --write`);
}

async function main() {
  const catalog = buildCatalog();
  const json = serializeCatalog(catalog);
  const markdown = renderMarkdown(catalog);
  if (process.argv.includes('--write')) {
    await Promise.all([writeFile(JSON_PATH, json), writeFile(MARKDOWN_PATH, markdown)]);
    return;
  }
  await Promise.all([checkFile(JSON_PATH, json), checkFile(MARKDOWN_PATH, markdown)]);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch(error => { console.error(error.message); process.exitCode = 1; });
}
