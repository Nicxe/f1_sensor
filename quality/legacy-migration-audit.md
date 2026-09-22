# Migrationsinventering kopplad till täckningskartan

Genereras med `node scripts/inventory_card_options.cjs` följt av `node scripts/audit_card_migration.mjs`.

Detta är ett underlag för A2 och F2. Varje rad i planens täckningskarta samt arkivaliaset är kopplad till sina statiskt identifierade inställningar och konverterarens observerade mål. [Rårapporten](legacy-migration-audit.json) innehåller värden, källrader, meddelanden och SHA-256 för underlaget.

**Ingen rad är här godkänd som full ersättare.** ”Överföring rapporterad” betyder att konverteraren rapporterar mapped eller changed för minst ett provvärde. Det bevisar inte att gammal och ny visning har samma betydelse. ”Granskning” betyder review för samtliga provvärden; även en annan giltig inställning kan ha missats av urvalet.

Varje inställning provas ensam och varje nyckelpar provas dessutom med den kartesiska produkten av rapportens representativa värden, medan övriga nycklar använder en deterministisk baslinje. För varje sådan flervalskonfiguration krävs fullständiga rapporteringsrader, varningsfri modulär konfiguration och exakt återställning av originalet. Detta är kombinationstäckning för observerade representanter, inte ett bevis för visuell eller beteendemässig paritet i alla värdedomäner. Gemensamma hjälpfunktioner, implicita standardvärden och manuell jämförelse återstår.

Inventeringen följer klasslokala metodargument till konfigurationsåtkomst, avgränsade bokstavliga loopdomäner, replaykortets deklarerade entitetsnycklar, formulärfält med selector och bokstavliga nycklar i getStubConfig. Ursprunget sparas som indirect_evidence och resolved_computed_access i [källinventeringen](legacy-card-options.json). Alla 26 nu observerade beräknade konfigurationsåtkomster har en avgränsad nyckeldomän; en ny olöst åtkomst gör den incheckade inventeringen inaktuell och underkänner kontrollen. Analysen är fortfarande inte en fullständig JavaScriptanalys och påstår inget om nycklar som skapas utanför de observerade vägarna.

shared_evidence kopplar uttryckliga installF1EntityAutoBinding-registreringar till respektive kort, inklusive f1_entry_id och källnycklarnas suffix. Funktionsbaserade suffix markeras som dynamiska. Kända installationer av typsnitt och spoilerskydd samt anrop till gemensamma tema-/typsnittseditorer räknas också in. Övriga hjälpfunktioner, standardvärden och dynamiska installationer behöver fortsatt granskning; registret påstår inte att de är uttömmande analyserade.

Arkivaliasets inventering omfattar dess egen setConfig samt ärvda resultatkortet och dess editor. Aliasets tvingade arkivläge och standardvärden behöver dessutom beteendeprov; antalet nycklar är inte ett bevis för identiska funktioner.

| Kort | Nya moduler | Statiska nycklar | Överföring rapporterad | Granskning för alla prov | Beräknade åtkomster | Flervalskonfigurationer |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| F1 Weekend Hub | overview, timeline, strategy, battles, telemetry | 9 | 9 | 0 | 0 | 231 |
| F1 Tyres Statistics | tyres | 19 | 19 | 0 | 0 | 756 |
| F1 Pit Stops & Tyres | pit_stops, tyres | 25 | 25 | 0 | 0 | 1247 |
| F1 Driver Lap Times | timing | 24 | 24 | 0 | 0 | 1244 |
| F1 Championship Standings Drivers | standings | 27 | 27 | 0 | 0 | 1562 |
| F1 Championship Standings Teams | standings | 24 | 24 | 0 | 0 | 1244 |
| F1 Season Progression | progression | 19 | 19 | 0 | 0 | 794 |
| F1 Results | results, archive | 35 | 35 | 0 | 0 | 2445 |
| F1 Lap Position Progression | archive | 16 | 16 | 0 | 0 | 572 |
| F1 Replay Control | replay | 25 | 25 | 0 | 0 | 1248 |
| F1 Track Map | map | 22 | 22 | 0 | 0 | 1144 |
| F1 Investigations & Penalties | incidents | 14 | 14 | 0 | 0 | 417 |
| F1 Track Limits | incidents | 14 | 14 | 0 | 0 | 417 |
| F1 Next Race Overview | overview, calendar, weather, weather | 17 | 17 | 0 | 0 | 610 |
| F1 Race Weather | weather, weather | 9 | 9 | 0 | 0 | 178 |
| F1 Season Calendar | calendar | 12 | 12 | 0 | 0 | 310 |
| F1 Live Session Status | overview, weather | 22 | 22 | 0 | 0 | 1054 |
| F1 Race Control | race_control | 12 | 12 | 0 | 0 | 385 |
| F1 FIA Documents | documents | 22 | 22 | 0 | 0 | 1098 |
| F1 Qualifying Timing | timing | 21 | 21 | 0 | 0 | 921 |
| F1 Free Practice Timing | timing | 28 | 28 | 0 | 0 | 1621 |
| F1 Race Lap | timing, pit_stops | 34 | 34 | 0 | 0 | 2445 |
| F1 Starting Grid | results | 21 | 21 | 0 | 0 | 879 |
| f1-session-archive-card (alias) | archive | 35 | 35 | 0 | 0 | 2445 |

Totalt provas 25 267 flervalskonfigurationer. De ger inga saknade rapporteringsrader, inga varningar i den nya konfigurationen och kan återställas exakt. 119 distinkta förändringar av status eller mål redovisas i rårapporten; de uppstår bland annat när motstridiga installations-/entitetsval eller synlighetsval kombineras och är därför granskningsunderlag, inte dolda antaganden.

## Återstående inställningar per kort

Nycklarna nedan gav enbart granskningsbesked i det angivna provurvalet. De är en konkret granskningskö, inte beslut att ta bort funktionerna.

### F1 Weekend Hub

Korttyp: `f1-weekend-hub-card`.

Inga i detta provurval.

### F1 Tyres Statistics

Korttyp: `f1-sensor-live-data-card`.

Inga i detta provurval.

### F1 Pit Stops & Tyres

Korttyp: `f1-pitstop-overview-card`.

Inga i detta provurval.

### F1 Driver Lap Times

Korttyp: `f1-driver-lap-times-card`.

Inga i detta provurval.

### F1 Championship Standings Drivers

Korttyp: `f1-championship-prediction-drivers-card`.

Inga i detta provurval.

### F1 Championship Standings Teams

Korttyp: `f1-championship-prediction-teams-card`.

Inga i detta provurval.

### F1 Season Progression

Korttyp: `f1-season-progression-card`.

Inga i detta provurval.

### F1 Results

Korttyp: `f1-last-race-results-card`.

Inga i detta provurval.

### F1 Lap Position Progression

Korttyp: `f1-lap-position-progression-card`.

Inga i detta provurval.

### F1 Replay Control

Korttyp: `f1-replay-control-card`.

Inga i detta provurval.

### F1 Track Map

Korttyp: `f1-track-map-card`.

Inga i detta provurval.

### F1 Investigations & Penalties

Korttyp: `f1-investigations-card`.

Inga i detta provurval.

### F1 Track Limits

Korttyp: `f1-track-limits-card`.

Inga i detta provurval.

### F1 Next Race Overview

Korttyp: `f1-next-race-card`.

Inga i detta provurval.

### F1 Race Weather

Korttyp: `f1-weather-card`.

Inga i detta provurval.

### F1 Season Calendar

Korttyp: `f1-season-calendar-card`.

Inga i detta provurval.

### F1 Live Session Status

Korttyp: `f1-live-session-card`.

Inga i detta provurval.

### F1 Race Control

Korttyp: `f1-race-control-card`.

Inga i detta provurval.

### F1 FIA Documents

Korttyp: `f1-fia-documents-card`.

Inga i detta provurval.

### F1 Qualifying Timing

Korttyp: `f1-qualifying-timing-card`.

Inga i detta provurval.

### F1 Free Practice Timing

Korttyp: `f1-practice-timing-card`.

Inga i detta provurval.

### F1 Race Lap

Korttyp: `f1-race-lap-card`.

Inga i detta provurval.

### F1 Starting Grid

Korttyp: `f1-starting-grid-card`.

Inga i detta provurval.

### f1-session-archive-card (alias)

Korttyp: `f1-session-archive-card`.

Inga i detta provurval.
