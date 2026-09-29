# F1 Sensor – versionsbehov och mätbar baslinje

Datum: 2026-09-14. Underlag för A6. Alla mätningar gäller lokal, ocommittad kod
på `feat/modular-f1-card`; ingen ny release eller generell kompatibilitetsnivå
är verifierad genom detta dokument.

## 1. Versionsgränser

| Gräns | Nuvarande kontrakt | Krav vid ändring |
| --- | --- | --- |
| Sparat kortformat | `version: 1` | Avvisa okänd version; migrera uttryckligt vid ändrad betydelse |
| Planerade låsta sessioner och egna mallar | V2 är specificerad, inte implementerad | Implementera migration och UI innan v2 accepteras |
| Integrationens version | Separat från kortformat | En integrationsrelease får inte användas som konfigurationsversion |
| Frontendresurs | SHA-256 över paketerade filnamn och innehåll, första 12 tecknen | Uppdatera hela filuppsättningen och resursens `?v=` tillsammans |
| Karta | Protokoll 2 för subscribe/resync | Avvisa/hantera avvikande format; behåll testad äldre backendkompatibilitet enligt dess kontrakt |
| Analysström | Protokoll 1, begärt och kontrollerat | Ny protokollversion kräver matchande adapter och felhantering |
| Replaytelemetri | Svar med protokoll 1 och förväntad session | Acceptera inte svar från annan session eller okänt format |
| Entity discovery och resultat-/varvarkiv | Inget explicit protokollfält i de nuvarande frontendförfrågningarna | Dokumentera/versionssätt brytande ändringar; anta inte att gamla backends kan svara |

Källor: [konfiguration](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/config.js),
[anslutningar](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js),
[telemetri](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/telemetry-data.js),
[arkiv](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/season-data.js),
[resursleverans](../custom_components/f1_sensor/frontend.py).

`hacs.json` anger fortfarande Home Assistant 2024.11.0. Det är metadata, inte
bevis för att den nya kortplattformen fungerar på den versionen. `manifest.json`
har utvecklingsvärdet 1.0.0; det är inte en publicerad lägstaversion för kortet.
Versionsstödet måste provas i en riktig HA-matris och metadata vid behov ändras
innan release. Påstå inte stöd för en äldre HA enbart för att en mockad editor
fungerar. Kärnkraven omfattar HA:s editor/formulär, kortåtgärder, locale-inställningar,
WebSocket-anslutning, resursladdning och integrationens egna kommandon.

## 2. API-ytor och behov

| Konsument | Befintlig frontendbegäran | Gräns som måste bevaras |
| --- | --- | --- |
| Installationsval | `f1_sensor/entities` | Rätt entry, upptäckta ID:n, inaktiverade funktioner och globala kontroller |
| Race Control | `f1_sensor/race_control_log/get` samt händelser | Historik plus inkommande händelser utan dubbletter/förlust |
| Analysmoduler | `f1_sensor/analysis/subscribe` | Delad ström, protokoll 1, städning och återanslutning |
| Karta | `f1_sensor/track_map/subscribe`, `f1_sensor/track_map/resync` | Protokoll 2, sekvens och geometri; luckor utlöser kontrollerad omsynk |
| Historiska resultat | `f1_sensor/history/catalog`, `results`, `laps` | Läsning för vald säsong/session, aldrig starta replay som bieffekt |
| Telemetri | `f1_sensor/analysis/telemetry_catalog`, `telemetry_compare` | Förväntad laddad session och användarens uttryckliga jämförelse |
| Livekontroller/replay | Upptäckta select/number/switch/button/media_player | Gällande tillstånd, behörigheter och korrekt åtgärdsräckvidd |

Analys och karta begär nu 500 ms throttling. Detta är ett klient-/protokollval,
inte en ny användarinställning för backendpollning. Kort får inte starta separata
strömmar för varje renderingscykel. Funktioner som saknas ska ge begriplig
reservvisning utan att andra fungerande moduler blockeras.

Återstående API-arbete: gemensam session-/seek-generation för kombinerade fält,
exakta tidsursprung per fält, v2:s låsta sessionsval och capability-baserad
versionsdiagnostik. Det ska förankras i A1:s datakontrakt. Ett valt frontendfilter
kan inte skapa data eller oberoende replaylägen som backend inte levererar.

## 3. Reproducerbar mätning

Kommando från repots rot:

```sh
F1_MAINTENANCE=1 npx playwright test frontend-tests/modular-performance.spec.js
```

[Testet](../frontend-tests/modular-performance.spec.js) kör Chromium med 32 förare,
100 registrerade varv per förare och 20 uppdateringar per scenario. Det mäter
rendering inklusive schemaläggning och bildrutor, p95 för uppdateringar, Long Task
API, förfrågningar/prenumerationer och frigjorda resurser. Externa loggor/flaggor
är avstängda. Ingen nätverksfördröjning till riktig HA eller verklig livefeed ingår.

Miljö: Apple M4, macOS/arm64, Node v26.7.0 och Playwright 1.63.0. Installerat
Playwright-manifest anger Chromium/Headless Shell 153.0.8010.12, revision 1243.
Rådata med miljö, tidpunkt och alla tre körningar finns i
[modular-performance-baseline.json](modular-performance-baseline.json).

| Scenario | Kort | Initial rendering, körning 1/2/3 (ms) | p95 uppdatering, 1/2/3 (ms) | Längsta registrerade task, 1/2/3 (ms) |
| --- | --- | --- | --- | --- |
| Enkel översikt och väder | 1 | 73,4 / 86,7 / 62,8 | 33,6 / 34,0 / 33,5 | 0 / 0 / 0 |
| Timing, varvdiagram, Race Control | 1 | 88,0 / 65,4 / 65,7 | 34,0 / 34,0 / 33,7 | 0 / 0 / 0 |
| Delad timing och Race Control | 10 | 116,0 / 116,4 / 116,6 | 33,9 / 34,0 / 33,7 | 56 / 55 / 0 |
| Samma med behåll sparad timingdata | 10 | 99,0 / 99,9 / 100,5 | 34,2 / 34,3 / 33,7 | 0 / 0 / 0 |

Noll i Long Task-kolumnen betyder ingen registrerad long task i testets fönster,
inte att inget arbete tog tid. p95 är den nittonde sorterade observationen av 20,
inte ett statistiskt säkerställt produktionsvärde. Minnesmätaren gav avrundade
10 000 000 byte före/efter och används därför inte som bevis för minnesbudget.

Alla tre körningar hade noll tjänsteanrop. De tre mer omfattande scenarierna hade
vardera två förfrågningar och tre prenumerationer, även med tio kort. Samtliga
visade 32 timingrader per kort och frigjorde resurser, händelselyssnare, grupper
och sparade snapshots efter borttagning.

## 4. Gränser och aktuellt resultat

[Nuvarande budgetar](performance-budgets.json) kräver rendering under 2 500 ms
och längsta registrerade task under 50 ms. Testet kontrollerar båda, tillsammans
med resursinvarianterna. p95 rapporteras men har ingen hård assertion i testet.
Den separata `realtime`-budgeten gäller ett annat fixtureflöde och ska inte
beskrivas som en verifierad gräns för dessa fyra modulscenarier.

**Baslinjen är inte genomgående godkänd:** körning 1 och 2 bröt mot 50 ms-gränsen
för tio delade kort; körning 3 passerade. Det sista gröna resultatet ersätter inte
de två avvikelserna. Budgeten har inte höjts och testet har inte fått retries.
Orsaken är ännu inte profilerad, så avvikelsen tillskrivs inte en viss ändring.

Nästa prestandaarbete ska lokalisera blockeringen i en trace/profil, skilja
kortmodell/rendering från fixture- och schemaläggningskostnad, och åtgärda
bekräftat kortarbete. Därefter körs samma scenarier och rådata jämförs med denna
baslinje. Om testets mätmetod behöver ändras ska skälet dokumenteras och båda
resultaten behållas; svagare mätning får inte användas för att dölja blockeringen.

## 5. Testmatris inför acceptans

- Behåll enhets-/browsertester för konfiguration, semantik, grupper, tidsformat,
  spoilerskydd, replay och avbrutna anrop. Kör fulla repo- och runtimekontroller
  vid kodändringar enligt projektets instruktioner.
- Mät kall första laddning separat från uppvärmd uppdatering. Prova aktiva
  loggor/flaggor, karta, telemetri, öppna detaljer och editorförhandsvisning.
- Prova flera relevanta fältstorlekar och sessionstyper, inte bara standardgrid.
- Mät på representativ mobil/surfplatta och med textförstoring/reduced motion.
  En snabb utvecklingsdator kan inte bevisa målgruppens upplevelse.
- Kontrollera heap och lyssnare under lång körning, upprepade vybyten,
  borttagning, återanslutning, replay-seek och sessionsbyten.
- Verifiera faktiska äldre/nya HA-versioner och berörda webbläsare innan en
  stödnivå publiceras. Kör releasens CI på rätt commit när publicering tillåts.

A6 specificerar versionsbehov och etablerar en mätbar baslinje. Prestandaavvikelsen
ovan är fortfarande öppen och ska lösas före slutlig acceptans. C7, E5 och F3/F6
är inte uppfyllda genom detta dokument.

## 6. Profilering av första rendering

En uppföljande instrumenterad körning med CDP:s CPU-profiler och timeline-trace
placerar den längsta huvudtrådsuppgiften mellan `ten-shared:start` och
`ten-shared:rendered`. Den var 60,82 ms, med Layout 29,46 ms, UpdateLayoutTree
18,93 ms och PrePaint 8,66 ms. De löpande uppdateringarna är inte den
identifierade fasen. Instrumentering kan påverka tiden, så siffrorna ersätter
inte de tre ordinarie körningarna. Nästlade tracehändelser överlappar och ska
inte summeras godtyckligt.

[Profilens sammanfattning](modular-performance-profile.json) behåller mätningen
och lokala sökvägar till full trace/CPU-profil. Den tillfälliga instrumenterade
testkopian är borttagen; ordinarie test och budget är oförändrade.

Nästa åtgärd är att prova avgränsning av kortens layout-/stilberäkning och mäta
samma första rendering igen. Kontroller får inte klippas, tabellernas kolumner
får inte bli oläsliga, och tillgänglighets- eller fokusflöden får inte försämras.
Ingen prestandafix är ännu genomförd eller godkänd.

## 7. Avgränsade optimeringsförsök

Fyra experiment kördes via tillfälliga testvarianter utan ändrad produktionskod.
[Full rådata](modular-performance-experiments.json) behåller alla utfall.

| Försök | Utfall | Bedömning |
| --- | --- | --- |
| Layout-/style-containment på kortet | Tiokortstoppen 54 ms | Inte tillräcklig förbättring |
| Blocklayout i stället för yttre flexbehållare för tidcell | Tiokortstoppen 54 ms | Inte tillräcklig förbättring |
| Tre kort per bildruta | Ingen registrerad long task; p95 för tio kort cirka 100 ms | En passerande mätning, men tydlig latenskostnad; inte införd |
| Fem kort per bildruta | p95 för tio kort cirka 67 ms; detaljerad vy gav 58 ms long task | Inte robust godkänd; inte införd |

Varje rad är ett utforskande enskilt försök, inte jämförbar statistisk säkerhet.
Ingen kandidat är levererad som fix. De tillfälliga testvarianterna är borttagna.
Nästa optimering måste minska eller fördela layoutarbete med verifierad effekt
över samtliga scenarier, samtidigt som uppdateringslatens och UI-kvalitet följs.
Att bara dela arbetet i fler bildrutor är ännu inte en accepterad lösning.

## 8. Införd första-renderingskö och uppföljning

En avgränsad kö för den första kortlayouten är nu införd. Högst tre kort som
ännu inte har modulnoder får påbörja rendering per bildruta. När modulnoderna
finns används den tidigare schemaläggningen för uppdateringar. Borttagning
avbokar väntande köplats och släpper uppdateringslöftet.

Tre ordinarie körningar efter ändringen passerade med oförändrade budgetar och
ingen registrerad long task. För tio delade kort var första rendering
150,0 / 150,1 / 166,5 ms och p95 uppdatering 33,9 / 33,8 / 33,4 ms. För tio kort
med sparad data var motsvarande värden 133,3 / 149,2 / 149,2 ms och
33,6 / 33,4 / 34,1 ms.

[Rådata](modular-performance-after-initial-batching.json) behåller alla scenarier
och kontrollresultat. Python-testsviten körde samtidigt; detta är lokala
observationer, inte en kontrollerad statistisk jämförelse. Initial rendering tar
cirka 34–51 ms längre i tiokortsfallet än den ursprungliga baslinjen, men ger
webbläsaren möjlighet att måla mellan grupper. Löpande uppdateringslatens ligger
kvar omkring 34 ms. Resursstädning, radantal och delade strömmar är verifierade.

Det specifika tiokortsfelet har därmed en verifierad lokal åtgärd. Kraven på
verkliga enheter, långa körningar och hela C7/E5/F3-matrisen kvarstår. Tidigare
misslyckade mätningar ovan är historiskt underlag och har inte raderats.

Ytterligare två avvisade försök under denna etapp gav 50 ms med fast tabellayout
och 52 ms med uppskjuten timingförklaring. De infördes inte; tabellens bredd-
regler och timingförklaringens beteende är oförändrade.
