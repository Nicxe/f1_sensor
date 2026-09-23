# F1 Sensor – räckvidd för val och åtgärder

Datum: 2026-09-14. Specifikation för A5 i kortplattformens plan.

Detta kontrakt skiljer visningsval från åtgärder som ändrar integrationen.
Nuvarande version och målkrav redovisas separat. Sparformat och framtida låsta
sessioner definieras i [konfigurationskontraktet](modular-configuration-contract.md).

## 1. Grundregel

En visningskontroll ska inte skriva till Home Assistant. En integrationsåtgärd
ska däremot ange vad den påverkar innan den utförs. Kontrollgrupper delar
uttryckligt valda visningsvärden; de är inte egna replaymotorer eller instanser
av Live Delay.

Standard är ett självständigt kort. Ett tillfälligt förarval skriver inte till
integrationens Favorite Driver-selector. Layout, flikar, färger och kolumner
ändrar inte datainsamlingen eller automationernas leverans.

## 2. Omfattningsmatris

| Kontroll | Räckvidd | Sparas var? | Tillåten effekt |
| --- | --- | --- | --- |
| Modulens fasta förare/team | En modul | Kortets dashboardkonfiguration | Filtrerar modulens presentation |
| Kortets standardfokus | Kortet | Kortets dashboardkonfiguration | Startvärde när kortet skapas |
| Tillfälligt förarfokus | Kortet, eller uttryckligt ansluten grupp | Aktuell frontendinstans | Ändrar visat urval |
| Kolumner, filter, modulordning, stil | Kortet/modulen | Dashboardkonfiguration via HA:s Spara | Renderar samma källor på annat sätt |
| Aktiv flik, öppna detaljer och timingförklaring | Den aktuella vyn i kortet | Tillfälligt minne | Visar/döljer lokalt innehåll |
| Frys vyn | Ett kort | Lokal snapshot tills återgång/ogiltigförklaring | Håller läsbilden stilla; stoppar inte backend |
| Dölj spoilers lokalt | Ett kort | Kortets konfiguration | Maskerar spoilers i kortet |
| Resultatarkivets säsong/evenemang/session | Arkivmodulen | Sparat standardval eller tillfälligt modulval | Läser historiskt underlag; startar inte replay |
| Telemetrijämförelse | Telemetrimodulen | Sparade val samt aktuell explicit begäran | Läser valda inspelade varv/kanaler |
| Live Delay | Vald F1-installation/entry | Integrationens kontroll och lagring | Ändrar leveransfördröjning, även för berörda automationer |
| Kalibrering | Vald F1-installation/entry | Integrationens kalibreringstillstånd | Väljer referens och beräknar/tillämpar Live Delay |
| Globalt No Spoiler Mode | Alla F1 Sensor-entries som den globala funktionen omfattar | Integrationens globala manager | Ändrar integrationens gemensamma skydd |
| Replay: välj, ladda, spela, pausa, seek, stoppa | Vald entrys backend-replay | Integrationens replaytillstånd | Ändrar replay som andra konsumenter kan följa |
| Konfigurerad HA-kortåtgärd | Enligt vald HA-åtgärd och mål | Kortets konfiguration | Kan navigera, öppna detaljer eller anropa en tjänst |
| Återställ/rensa integrationshistorik | Berörd backendlagring | Integrationens lagring | Destruktiv dataåtgärd, aldrig en följd av lokal filtrering |

Sista raden är ett gränskrav, inte ett påstående om att en sådan knapp finns i
nya kortet. Om den införs ska lagringens omfattning beskrivas uttryckligt och
bekräftelse ske separat från att stänga/rensa en lokal vy.

## 3. Kontrollgrupper

### Nuvarande v1

Gruppen identifieras av anslutningsobjekt, entry, dashboard, vy och normaliserat
gruppnamn. Två lika gruppnamn på olika vyer eller installationer är olika grupper.
Samma namn på två enheter innebär inte synkronisering mellan enheterna.

Gruppkanalen tillåter enbart strängvärden för `driver` och `team`. Replay,
spoilers, Live Delay och okända nycklar får inte passera som åtgärder i kanalen.
Nuvarande kortets förarväljare publicerar förarfokus; stöd för ett teamvärde i
kanalen innebär inte att en separat tillfällig teamväljare redan är levererad.

En ny deltagare får gruppens aktuella värden. Den sista deltagarens borttagning
frigör gruppen. Värdena skrivs inte till localStorage eller HA:s dashboard.
Omladdning eller byte av anslutning kan därför ge kortets sparade standardvärden.
Det är inte ett felaktigt löfte om personliga val mellan olika enheter.

Prioritet för aktuellt förar-/teamurval är uttryckligt modulvärde före tillfälligt
kort-/gruppfokus. Ett tomt modulvärde betyder att modulen får följa fokus.
Sparat kortfokus är ett startvärde, inte ett separat lås som alltid övertrumfar gruppen.

### Målmodell för sessionsval

V2:s `selection` och `context.share` i konfigurationskontraktet är ännu inte
implementerade. De ska följa samma isolering och följande regler:

1. Explicit låst modul följer sitt eget sammanhang.
2. Låst kort följer sitt eget sammanhang före gruppen.
3. Endast kort som uttryckligen deltar i delning av sessionsval följer gruppval.
4. Övriga kort följer sitt eget automatiska sammanhang.

Ett historiskt sessionsval ska aldrig ladda en replay som bieffekt. Om data
saknas visas det för det låsta sammanhanget; byt inte tyst till en annan session.
Kontrollgruppen får aldrig erbjuda illusionen av olika uppspelningspositioner
när backend bara har en gemensam replay för den berörda entryn.

## 4. Frysning, skydd och tillfälliga val

Frysning är en läshjälp. De ordinarie källorna kan fortsätta samla data, andra
kort uppdateras och integrationens automationer fortsätter. Följande gäller:

- Fryst läsvy ska märkas och ha en enkel återgång till aktuell data.
- Replay-/Live Delay-/kalibreringskontroller i den frysta vyn är skrivskyddade.
- Nytt aktivt spoilerskydd ska omedelbart skydda även en tidigare fryst bild.
- Byte av entry, session, anslutning eller uppspelningsgeneration får inte
  presentera en gammal bild under ett nytt sammanhang.
- Mottaget gruppfokus får inte ge en rubrik eller väljare för en förare medan
  den frysta tabellen fortfarande visar en annan utan begriplig förklaring.
- Att dölja en modul/flik eller ta bort kortet får inte pausa/stoppa replay.

Fryst gruppfokus och förarlista sparas nu tillsammans med läsbilden. Gruppens
nya fokus tas emot men ändrar inte den frysta väljaren; ett besked visas och
Fortsätt följer det senaste valet. Ett eget förarval avslutar frysningen.
Resursavslut, inklusive borttaget kort eller ny anslutning, släpper den frysta
bilden. Browsertest täcker gruppbyte, ändrad förarlista, eget val och borttagning.
Sessions-, replay- och Live Delay-generationen sparas nu vid frysning. Om den ändras visas ett besked, medan läsbilden och dess ursprungliga sammanhang ligger kvar tills användaren väljer Fortsätt. Aktivt eller okänt spoilerskydd fortsätter att skydda även den frysta bilden. Frysning hämtar generation och modeller från samma aktuella HA-underlag. Fullständiga entry-/anslutnings-/replayövergångar kräver fortfarande granskning.

Lokalt Visa får aldrig kringgå aktivt globalt spoilerskydd. Lokalt Dölj ändrar
inte den globala switchen. Att stänga av globalt skydd är en separat uttrycklig
åtgärd; nuvarande UI begär bekräftelse knuten till aktuellt skyddstillstånd.

## 5. Integrationsåtgärder och samtidighet

Åtgärder ska använda upptäckta entity-ID:n och entry-identitet, inte hårdkodade
standardnamn. Kontrollens senaste tillstånd, tillgänglighet och tillåtna värden
kontrolleras vid klicket. En gammal dialog eller sent svar får inte styra en ny
entry/session. Fel ska kunna visas utan att UI påstår att åtgärden lyckades.

Nuvarande Live Delay och kalibrering använder gemensamt skrivlås för entryn i
samma frontendanslutning. Övriga kontrollskrivningar har entitetslås. Det skyddar
mot samtidiga kortanrop där, men är inte en distribuerad transaktion mellan
användare, webbläsare eller enheter.

Replay har en väntande begäran per kort och ett gemensamt kommandolås per entry
i samma frontendanslutning. Låsningen gäller även olika kontrollentiteter, som
laddning och uppdatering av sessionslistan. Ett blockerat kommando skickas inte
och köas inte; användaren får ett besked och kan försöka igen efter kontroll av
aktuellt tillstånd. Låset släpps när tjänsteanropet avslutas eller misslyckas.
Det väntar inte på att en hel replayhämtning eller uppspelning ska bli klar;
backendens bekräftade tillstånd och kontrollernas vanliga validering gäller då.
Detta är inte distribuerad serialisering mellan separata enheter. E3/C7 ska
fortsatt verifiera alla sådana samtidighets- och livscykelövergångar.

Konfigurerade HA-kortåtgärder är ett separat användarvalt beteende. Där det finns
tjänsteanrop bestäms effekten av den konfigurationen. De ska inte beskrivas som
lokala visningsval bara för att de startas från kortets rubrik.

## 6. Förhandsvisning och editor

Demonstrationsdata får aldrig anropa kontrolltjänster. HA:s booleska previewläge
kan upptäcka riktiga källor men får inte utföra tjänste- eller kortåtgärder.
Färgval, omordning, mallbyte, import och förarval i preview ändrar endast utkastet.
Att välja en demonstrationssession får inte välja eller ladda en riktig replay.

Dashboardens sparade konfiguration ändras först genom HA:s Spara. Avbryt ska
lämna den sparade konfigurationen intakt. Import ska visa skillnaden och vara
återställbar enligt konfigurationskontraktet. Permanent sparande över flera
enheter ska verifieras genom faktisk omladdning av dashboarden; tillfälligt
fokus och öppna detaljer ingår inte i det löftet.

## 7. UI-formuleringar

| Typ | Svensk kärntext | Engelsk kärntext |
| --- | --- | --- |
| Lokal frysning | Endast detta kort är pausat | Only this card is paused |
| Gruppfokus | Delar förarfokus i denna vy | Shares driver focus in this view |
| Live Delay | Påverkar leverans och automationer för denna F1-installation | Affects delivery and automations for this F1 installation |
| Globalt skydd | Påverkar alla F1 Sensor-installationer här | Affects all F1 Sensor entries here |
| Replay | Styr denna installations gemensamma replay | Controls this entry's shared replay |
| Historiskt urval | Visar arkivdata; startar ingen uppspelning | Shows archived data; does not start playback |

Tabellen är ett språkkrav; exakta befintliga texter kan vara längre eller delas
över rubrik och förklaring. Undvik tekniska ord som entry i svensk normalvy och
använd installationsnamnet där flera installationer annars kan förväxlas.

## 8. Bevis och acceptans

| Kontroll | Befintlig evidens | Kvarstående grind |
| --- | --- | --- |
| Gruppisolering och tillåtna nycklar | `modular-connection.test.mjs`, `watchGroup` | Komplett UI-provning av låsta moduler och vybyten |
| Förarfokus och modulprioritet | `card.js`, `timingRows` i `data.js`, `frozen-focus.spec.js` | Samtliga modulers adapterprioritet och full sessionslivscykel |
| Preview utan åtgärder | `modular.spec.js`, `calibration.spec.js` | Hela editorns/modulkatalogens matris |
| Delay, skydd, inaktuellt underlag | `modular-viewing.test.mjs`, `viewing.spec.js`, katalogdriven skyddsmatris i `modular.spec.js` | Verklig flerenhets- och uthållighetsmatris under C7/F3 |
| Kalibrering och skrivlås | `modular-calibration.test.mjs`, `calibration.spec.js` | Samspel med samtidiga externa konsumenter |
| Replay, seek, gammal session | `modular-replay.test.mjs`, `modular.spec.js`, `replay-concurrency.spec.js` | Flera enheter och hela E3/E5 |
| Frigör resurser utan replaystopp | `modular-connection.test.mjs` | Alla borttagnings-/återanslutningssekvenser |
| Global skyddsomfattning | `switch.py`, gemensam NoSpoilerModeManager | Flera riktiga entries och alla skyddade konsumenter |

Källor:

- [Kortets hantering av fokus och åtgärder](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/card.js)
- [Grupper och skrivlås](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/connection.js)
- [Visningskontroller och bekräftelse](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/viewing-controls.js)
- [Globalt spoilerskydd](../custom_components/f1_sensor/switch.py)
- [Anslutningstester](../frontend-tests/unit/modular-connection.test.mjs)
- [Visningskontrolltester](../frontend-tests/unit/modular-viewing.test.mjs)
- [Replaytester](../frontend-tests/unit/modular-replay.test.mjs)
- [Kalibreringstester](../frontend-tests/unit/modular-calibration.test.mjs)

A5, E4 och den samlade automatiska E5-matrisen är verifierade inom detta
kontrakts implementerade omfattning. C6/C7 och F3 är inte klara bara för att
räckvidden är dokumenterad eller en enskild gräns har ett passerande test.


### Eget modulurval

`focus_mode=independent` använder modulens egna förar-/teamfilter och ignorerar kortets tillfälliga och delade fokus. Ett tomt filter omfattar alla i den dimensionen. `inherit` är standard och behåller tidigare beteende, inklusive uttryckliga modulfilter. Övriga filter, sessioner, tillgänglighet och spoilerskydd gäller i båda lägena. Detta är inte ett generellt lås av säsong eller session. UI-val, sparad konfiguration och två kopplade kort har browserprov med följande, oberoende, låst och oförenligt förar-/teamurval.
