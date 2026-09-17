/** Observed conversion coverage, not a claim of equivalent rendering or exhaustive inputs. */
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { isDeepStrictEqual } from 'node:util';
import { LEGACY_ENTITY_BINDINGS, LEGACY_MIGRATIONS, proposeMigration, restoreLegacy } from '../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js';
import { configWarnings } from '../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js';

const root = new URL('../', import.meta.url);
const read = path => fs.readFileSync(new URL(path, root), 'utf8');
const inventory = JSON.parse(read('quality/legacy-card-options.json'));
const fingerprint = paths => Object.fromEntries(paths.map(path => [path, createHash('sha256').update(read(path)).digest('hex')]));
const auditEntityId = source => `${source === 'replay_player' ? 'media_player' : source.endsWith('_select') ? 'select' : ['formation_start', 'overtake_mode'].includes(source) ? 'binary_sensor' : source === 'replay_status' || source === 'straight_mode' ? 'sensor' : 'button'}.audit_${source}`;
const boundSources = [...new Set(Object.values(LEGACY_ENTITY_BINDINGS).flatMap(bindings => Object.values(bindings)))];
const entry = { entry_id: 'audit', title: 'Audit', entities: { driver_positions: 'sensor.audit_source', ...Object.fromEntries(boundSources.map(source => [source, auditEntityId(source)])) }, global_entities: { no_spoiler_mode: 'switch.audit_spoilers' } };
const values = (key, type) => {
  if (/^(show_|hide_|prefer_|dim_|highlight_|invert_|open_)/.test(key)) return [false, true];
  if (/^color_/.test(key)) return ['#2266bb', 'rgb(34, 102, 187)'];
  if (key === 'tap_action') return [{ action: 'more-info' }];
  if (key === 'title') return ['My race'];
  if (key === 'compounds') return [['SOFT', 'MEDIUM'], ['WET']];
  if (key === 'auth_status_entity') return ['sensor.f1_f1tv_token_status', 'sensor.unmatched'];
  if (/entity$/.test(key)) {
    const source = LEGACY_ENTITY_BINDINGS[type]?.[key];
    return [source ? entry.entities[source] : 'sensor.audit_source', 'sensor.unmatched'];
  }
  if (/entry_id$/.test(key)) return ['audit', 'unmatched'];
  if (key === 'year' || key === 'history_year') return [2025];
  if (key === 'chart_height' && type === 'f1-season-progression-card') return [240, 320, 520];
  if (key === 'chart_height' && type === 'f1-lap-position-progression-card') return [300, 420, 720];
  if (key === 'display_mode' && type === 'f1-replay-control-card') return ['full', 'compact'];
  if (key === 'display_mode' && type === 'f1-starting-grid-card') return ['grid', 'table'];
  const choices = {
    theme_mode: ['auto', 'dark', 'light'], font_style: ['system', 'wide', 'balanced'],
    team_logo_style: ['auto', 'color', 'white'], sector_display_mode: ['current', 'personal_best'],
    gap_mode: ['ahead', 'leader', 'off'], mode: ['drivers', 'constructors'],
    display_mode: ['list', 'latest', 'banner'], driver_label_mode: ['tla', 'number'],
    driver_image_type: ['team_logo', 'headshot'],
    layout_mode: ['auto', 'compact', 'full'], track_status_line_mode: ['accent', 'full', 'off'],
    sort_order: ['asc', 'desc'], default_scope: ['archive', 'current'],
    default_view: ['overview', 'timeline', 'strategy', 'telemetry', 'battles'],
    legend_position: ['bottom', 'left', 'right'],
    throttle_ms: [100, 500, 5000],
  };
  return choices[key] ?? [0, 5, 'auto'];
};
const cards = [...inventory.cards, ...inventory.aliases.map(alias => {
  const parent = inventory.cards.find(card => card.type === alias.target);
  assert.ok(parent, `${alias.type}: missing parent`);
  return { ...parent, ...alias, name: `${alias.type} (alias)`, card: {
    fields: [...parent.card.fields, ...alias.card.fields],
    computed_access: [...parent.card.computed_access, ...alias.card.computed_access],
  } };
})].map(card => {
  assert.ok(LEGACY_MIGRATIONS[card.type], card.type);
  const keys = [...new Set([...card.card.fields, ...card.editor.fields].map(field => field.key))].sort();
  const fields = keys.map(key => {
    const observations = values(key, card.type).map(value => {
      const original = { type: `custom:${card.type}`, [key]: value };
      const { config, rows } = proposeMigration(original, { entries: [entry] });
      assert.deepEqual(restoreLegacy(config), original, `${card.type}.${key}: backup`);
      const row = rows.find(row => row.path === key);
      assert.ok(row, `${card.type}.${key}: missing report`);
      return { value, status: row.status, target: row.target, explanation: row.message.sv };
    });
    return { key, lines: [...new Set([...card.card.fields, ...card.editor.fields].filter(field => field.key === key).flatMap(field => field.lines))].sort((a, b) => a - b),
      observed: observations.some(row => row.status !== 'review') ? 'conversion_reported_for_some_probes' : 'review_for_all_probes', observations };
  });
  const representative = Object.fromEntries(fields.map(field => [field.key, field.observations.map(observation => observation.value)]));
  const baseline = { type: `custom:${card.type}`, ...Object.fromEntries(keys.map(key => [key, representative[key][0]])) };
  const combinations = [baseline];
  for (let left = 0; left < keys.length; left++) for (let right = left + 1; right < keys.length; right++) {
    for (const leftValue of representative[keys[left]]) for (const rightValue of representative[keys[right]]) {
      combinations.push({ ...baseline, [keys[left]]: leftValue, [keys[right]]: rightValue });
    }
  }
  const reportingVariations = new Set();
  const pairwise = { configurations: combinations.length, key_pairs: keys.length * (keys.length - 1) / 2, missing_rows: 0, warning_configurations: 0, reporting_variations: [] };
  for (const original of combinations) {
    const { config, rows } = proposeMigration(original, { entries: [entry] });
    assert.deepEqual(restoreLegacy(config), original, `${card.type}: pairwise backup`);
    const missing = keys.filter(key => !rows.some(row => row.path === key));
    pairwise.missing_rows += missing.length;
    assert.deepEqual(missing, [], `${card.type}: pairwise report rows`);
    for (const field of fields) {
      const expected = field.observations.find(observation => isDeepStrictEqual(observation.value, original[field.key]));
      const actual = rows.find(row => row.path === field.key);
      if (!isDeepStrictEqual([actual.status, actual.target], [expected.status, expected.target])) reportingVariations.add(`${field.key}: ${expected.status}:${expected.target} -> ${actual.status}:${actual.target}`);
    }
    if (configWarnings(config).length) pairwise.warning_configurations++;
  }
  pairwise.reporting_variations = [...reportingVariations].sort();
  assert.equal(pairwise.warning_configurations, 0, `${card.type}: pairwise configuration warnings`);
  return { type: card.type, name: card.name, modules: LEGACY_MIGRATIONS[card.type].map(module => module.type), fields,
    computed_access: [...card.card.computed_access, ...card.editor.computed_access], pairwise };
});
const result = {
  format_version: 2,
  method: 'Each inventoried card/editor key is probed separately with the explicit representative values below. Every pair of keys is also exercised with the Cartesian product of those representative values while all other keys retain a deterministic baseline. The inventory includes bounded domains for every currently observed computed configuration access. Report status and target come from the actual converter; exact restoration, complete report rows and warning-free modular configuration are asserted for both individual and pairwise probes. This does not prove semantic rendering equivalence, full legacy defaults, full value-domain coverage or unobserved inherited helper behavior.',
  fingerprints: fingerprint(['quality/legacy-card-options.json', inventory.source, 'custom_components/f1_sensor/www/f1-sensor-live-data-card/platform/entity-resolver.js', 'custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js', 'custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js', 'custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js', 'scripts/audit_card_migration.mjs', 'scripts/inventory_card_options.cjs', 'scripts/legacy_config_analysis.cjs']),
  cards,
};
const lines = [
  '# Migrationsinventering kopplad till täckningskartan', '',
  'Genereras med `node scripts/inventory_card_options.cjs` följt av `node scripts/audit_card_migration.mjs`.', '',
  'Detta är ett underlag för A2 och F2. Varje rad i planens täckningskarta samt arkivaliaset är kopplad till sina statiskt identifierade inställningar och konverterarens observerade mål. [Rårapporten](legacy-migration-audit.json) innehåller värden, källrader, meddelanden och SHA-256 för underlaget.', '',
  '**Ingen rad är här godkänd som full ersättare.** ”Överföring rapporterad” betyder att konverteraren rapporterar mapped eller changed för minst ett provvärde. Det bevisar inte att gammal och ny visning har samma betydelse. ”Granskning” betyder review för samtliga provvärden; även en annan giltig inställning kan ha missats av urvalet.', '',
  'Varje inställning provas ensam och varje nyckelpar provas dessutom med den kartesiska produkten av rapportens representativa värden, medan övriga nycklar använder en deterministisk baslinje. För varje sådan flervalskonfiguration krävs fullständiga rapporteringsrader, varningsfri modulär konfiguration och exakt återställning av originalet. Detta är kombinationstäckning för observerade representanter, inte ett bevis för visuell eller beteendemässig paritet i alla värdedomäner. Gemensamma hjälpfunktioner, implicita standardvärden och manuell jämförelse återstår.', '',
  'Inventeringen följer klasslokala metodargument till konfigurationsåtkomst, avgränsade bokstavliga loopdomäner, replaykortets deklarerade entitetsnycklar, formulärfält med selector och bokstavliga nycklar i getStubConfig. Ursprunget sparas som indirect_evidence och resolved_computed_access i [källinventeringen](legacy-card-options.json). Alla 26 nu observerade beräknade konfigurationsåtkomster har en avgränsad nyckeldomän; en ny olöst åtkomst gör den incheckade inventeringen inaktuell och underkänner kontrollen. Analysen är fortfarande inte en fullständig JavaScriptanalys och påstår inget om nycklar som skapas utanför de observerade vägarna.', '',
  'shared_evidence kopplar uttryckliga installF1EntityAutoBinding-registreringar till respektive kort, inklusive f1_entry_id och källnycklarnas suffix. Funktionsbaserade suffix markeras som dynamiska. Kända installationer av typsnitt och spoilerskydd samt anrop till gemensamma tema-/typsnittseditorer räknas också in. Övriga hjälpfunktioner, standardvärden och dynamiska installationer behöver fortsatt granskning; registret påstår inte att de är uttömmande analyserade.', '',
  'Arkivaliasets inventering omfattar dess egen setConfig samt ärvda resultatkortet och dess editor. Aliasets tvingade arkivläge och standardvärden behöver dessutom beteendeprov; antalet nycklar är inte ett bevis för identiska funktioner.', '',
  '| Kort | Nya moduler | Statiska nycklar | Överföring rapporterad | Granskning för alla prov | Beräknade åtkomster | Flervalskonfigurationer |',
  '| --- | --- | ---: | ---: | ---: | ---: | ---: |',
  ...cards.map(card => `| ${card.name} | ${card.modules.join(', ')} | ${card.fields.length} | ${card.fields.filter(field => field.observed === 'conversion_reported_for_some_probes').length} | ${card.fields.filter(field => field.observed === 'review_for_all_probes').length} | ${card.computed_access.length} | ${card.pairwise.configurations} |`), '',
  `Totalt provas ${cards.reduce((n, card) => n + card.pairwise.configurations, 0).toLocaleString('sv-SE')} flervalskonfigurationer. De ger inga saknade rapporteringsrader, inga varningar i den nya konfigurationen och kan återställas exakt. ${cards.reduce((n, card) => n + card.pairwise.reporting_variations.length, 0)} distinkta förändringar av status eller mål redovisas i rårapporten; de uppstår bland annat när motstridiga installations-/entitetsval eller synlighetsval kombineras och är därför granskningsunderlag, inte dolda antaganden.`, '',
  '## Återstående inställningar per kort', '',
  'Nycklarna nedan gav enbart granskningsbesked i det angivna provurvalet. De är en konkret granskningskö, inte beslut att ta bort funktionerna.', '',
  ...cards.flatMap(card => [`### ${card.name}`, '', `Korttyp: \`${card.type}\`.`, '', card.fields.filter(field => field.observed === 'review_for_all_probes').map(field => `\`${field.key}\``).join(', ') || 'Inga i detta provurval.', '']),
];
const destinations = [[new URL('quality/legacy-migration-audit.json', root), `${JSON.stringify(result, null, 2)}\n`], [new URL('quality/legacy-migration-audit.md', root), `${lines.join('\n')}\n`]];
if (process.argv.includes('--check')) {
  for (const [destination, rendered] of destinations) if (fs.readFileSync(destination, 'utf8') !== rendered) throw new Error(`${destination.pathname} is stale; run this script without --check`);
} else for (const [destination, rendered] of destinations) fs.writeFileSync(destination, rendered);
console.log(JSON.stringify({ cards: cards.length, keys: cards.reduce((n, card) => n + card.fields.length, 0), probes: cards.reduce((n, card) => n + card.fields.reduce((total, field) => total + field.observations.length, 0), 0), pairwiseConfigurations: cards.reduce((n, card) => n + card.pairwise.configurations, 0), reviewOnly: cards.reduce((n, card) => n + card.fields.filter(field => field.observed === 'review_for_all_probes').length, 0) }));
