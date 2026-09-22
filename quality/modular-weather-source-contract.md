# Väder: källval, automatisk visning och migration

Status: källkontraktet är implementerat och automatiskt verifierat för A1/E4/E5,
granskat 2026-09-16. Källresolver, automatisk fältprofil, editorval, migration till
två vädermoduler, mallar och temperatur-/vindomräkning finns lokalt. Verklig
livehelg och full runtimeacceptans återstår under D2/F3; manuell migrationsparitet
återstår under F2. Befintliga manuella väderlägen finns kvar.

## Bekräftat nuläge

Det gamla `resolveF1WeatherComparison` väljer banväder när `prefer_live_weather` inte är false, sessionsstatus är `pre`, `live`, `suspended` eller `break` och användbara banmätningar finns. Saknas själva statusentiteten kan det ändå välja banväder. Raceprognosen väljs separat från väderentiteten. Valet gäller hela aktuellt-blocket; frånvarande livevärden ersätts inte godtyckligt med prognosvärden. Temperatur och vind har dessutom enhetskonvertering i det gamla presentationslagret.

Nya `weatherValues` har fyra manuella innehållslägen: `weather_overview`, `current_conditions`, `race_forecast`, `track_conditions`, samt `automatic_conditions`. De läser en primär källa åt gången. `weather_overview` visar vissa current-fält samt regnsannolikhet inför racestart från samma väderentitet. Migrationen använder nu separata moduler för aktuellt väder och raceprognos. `prefer_live_weather: false` väljer `current_conditions`, annars är utgångspunkten `automatic_conditions`. `show_weather` styr båda modulerna, oberoende av nycklarnas ordning.

Den nuvarande sparade läsbilden väljer primärkälla från modulens innehåll. Banväder är sessionsbundet och känsligt för spoilerskydd; vanligt väder är det inte. En ändring som bara lägger på livevärden efter denna gräns skulle kunna kombinera sparad prognosdata med nya banmätningar och missa skyddet.

Källor:

- [Gamla vädervalet och konverteringar](../custom_components/f1_sensor/www/f1-sensor-live-data-card/f1-sensor-live-data-card.js)
- [Nya väderadaptern, sessionContext och RetainedSources](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js)
- [Fältdefinitioner och innehållsprofiler](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/catalog.js)
- [Kortets skyddskontroll och presentation](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/card.js)
- [Befintlig migration](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/migration.js)

## Föreslagen användarupplevelse

Utöka vädermodulens källväljare med **Automatiskt aktuellt väder**. Det läget visar ett enda aktuellt block som kan byta mellan vanligt aktuellt väder och banobservationer. Raceprognosen är en separat instans av samma vädermodul. Användaren kan behålla båda, välja ordning eller ta bort den ena i samma korteditor.

Befintligt manuellt banväder ska fortsatt vara ett uttryckligt val utan automatisk prognosreserv. Befintliga sparade moduler ska inte ändra källa enbart genom uppgradering. Nytt automatiskt beteende väljs i UI, via en ny mall eller genom en granskad migration.

Blocken anger vad värdena betyder: aktuellt väder, banobservationer, inspelad replay respektive prognos inför racestart. Leverantörstexter och uppdateringsrader återinförs inte. Egna kolumner/fält, färger, flaggor, täthet och tillgänglighetsval förblir oberoende av källvalet.

## Val av källa

| Situation | Automatiskt aktuellt väder | Separat raceprognos |
| --- | --- | --- |
| Bekräftad aktiv sessionsstatus och användbara banvärden | Banobservationer, bundna till den tillgängliga sessionen | Publicerad prognos från väderentiteten |
| Aktiv session men inga användbara banvärden | Aktuellt väder från väderentiteten | Publicerad prognos |
| Mellan sessioner eller inaktiv session | Aktuellt väder från väderentiteten | Publicerad prognos |
| Statusentitet saknas, är otillgänglig eller har okänd status | Aktuellt väder; inget antagande om aktiv session | Publicerad prognos |
| Replay med giltigt sammanhang | Inspelade banobservationer när de finns och är tillåtna | Tydligt separat aktuell prognos; aldrig märkt som replayväder |
| Skydd aktivt eller skyddsläge okänt när banväder valts | Skyddsbesked för det känsliga blocket | Får fortsätta som offentligt prognosblock |
| Frånkoppling | Följ vald policy för saknad/sparad data | Följ sin egen policy |
| Manuell banvädermodul utan banvärden | Besked om saknad banmätning, ingen tyst annan källa | Påverkar inte prognosmodulen |

Att avstå från banväder när statusentiteten saknas är en avsiktlig skillnad mot den gamla reservvägen. Migrationen måste beskriva detta. Den aktuella datastrukturen kan inte bevisa observationens exakta ålder; använd inte HA:s mottagningstid som om den vore mättid.

## Implementation i beroendeordning

1. Lägg en ren, gemensam källresolver före fältdefinition, skyddskontroll och snapshotval. Den ska returnera vald källa, effektivt innehåll, sammanhang och orsak. Kort, adapter och editor får inte implementera olika urvalsregler.
2. Vald källa ska styra fältens sökvägar, enheter, betydelser, tillgänglighet och sammanhang. Behåll användarens fältval vid växling. Fält som saknas i vald källa visas som saknade; nederbördsmängd och regnindikator får aldrig byta betydelse under samma fält.
3. Den automatiska profilen behöver unionen av relevanta fält i editorn. Runtime ska bara läsa fälten enligt den faktiskt valda källan. Regnsannolikhet, detektion av regn och nederbördsmängd är separata storheter.
4. Primärkälla, skydd och sessionsbindning måste räknas ut innan `RetainedSources.select`. En sparad uppsättning får inte byggas med nya beroenden från en annan källa. Byte från väder till banväder eller tvärtom ogiltigförklarar föregående snapshot.
5. Bevara befintliga spärrar vid spoilerskydd, Live Delay, seek, sessionsbyte och borttagning. Fryst läsvy fryser även vald källa och dess beskrivning. Återupptagning väljer om mot aktuell data; skydd får bryta frysningen.
6. Redovisa respektive blocks eget tävlings-/sessionssammanhang. Om aktuell replay och prognos gäller olika tävlingar ska de inte få en gemensam rubrik som påstår att prognosen hör till replayn.
7. Lägg till det nya källvalet, fältkatalogen och mallarna i editorn. Export/import och omladdning ska bevara valet och egna fält. Uppdatera schema-/konfigurationsdokumentationen först när beteendet finns.
8. Utöka migreringsförslaget för Race Weather och Next Race Overview med två vädermoduler: aktuellt block och raceprognos. `prefer_live_weather: false` ger vanligt aktuellt väder; true eller den gamla implicita standarden ger automatiskt aktuellt väder. Originalet och granskningsrapporten bevaras.
9. Hantera kombinationen `show_weather: false` för båda vädermodulerna. Enbart första träffen via `find('weather')` är inte tillräckligt när samma kort har två vädermoduler. Kontrollera också ordningsoberoende flaggor och att konverteringsrapporten pekar på båda målen.
10. Verifiera normaliserade enheter mot källorna. Knyt inte UI:s enhetssträng till råvärden i en annan enhet; kontrollera °C/°F, m/s och HA:s valda enhet där konvertering ska ske.

## Acceptansmatris

- Automatik på/av, alla fyra aktiva statusar, inaktiv/okänd/saknad status samt frånkoppling.
- Livekälla komplett, partiell, tom, inaktiverad och otillgänglig; nollvärden och regnindikator false är giltiga värden.
- Raceprognosen ändras inte när aktuellt block växlar källa, och varje block visar sitt riktiga sammanhang.
- Skydd aktivt/okänt och egen lokal döljning: inga banvärden i kort, detaljer, frysta modeller eller förhandsvisning av riktig data.
- Behåll sparad data vid båda källorna; byte av källa, entry, session, replay-generation och Live Delay får inte blanda snapshots.
- Frysning/återupptagning vid källbyte samt två kort med olika källval; inga oavsiktliga tjänsteanrop.
- UI-val, omordning av två vädermoduler, egna fält, export/import och full omladdning.
- Migration med saknad/true/false preferens och show_weather, godtycklig nyckelordning, avbryt och exakt återställning.
- Läsbarhet i smal vy, tangentbord, skärmläsarnamn och hög kontrast; prognos, observation och regnindikator får inte skiljas åt enbart med färg.
- Verklig HA-visning med aktuella källor; dokumentera vilka grenar som endast kunnat provas med fixturedata.

Detta underlag stänger ingen implementations- eller releasegrind. Resolvern väljer källa före spoilerskydd och snapshotval. Automatiska fält läser bara den valda källan. Enhetstester täcker aktiva/inaktiva/okända statusar, partiella mätningar, giltiga nollvärden, frånkoppling och snapshotbyte. Ett reproducerat fel där frånkoppling tyst valde prognos är korrigerat: anslutningsstatus styr tillgängligheten, men byter inte själv den valda källan. Migreringen har enhetstester för saknad/true/false preferens och synlighet, omvänd nyckelordning och exakt återställning. Väderjämförelse- och helgmallen använder nu två väderblock. Temperatur-/vindomräkning och editoromladdning med egna fält är testade. Den återstående acceptansmatrisen, inklusive verkliga källbyten i HAdev, är fortfarande öppen.


### Observerat byte av datasammanhang

Kortet spärrar nu oförändrat banväder efter observerat sessionsbyte, ändrad Live Delay, byte av replay-session eller seek/bakåtspolning. Spärren gäller automatiskt och manuellt banväder oavsett vald policy för saknad data. En ny väderuppdatering släpper spärren; enbart återskapade HA-objekt gör det inte. Raceprognosen påverkas inte. Detta bevisar ingen exakt mättid eller ålder: källan saknar sådan metadata. Första laddning utan föregående sammanhang och redan frysta vyers fullständiga replay-/delaybeteende kräver fortsatt separat acceptans.
