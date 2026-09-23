# F1 Sensor – kontrakt för färger, former, pilar och varv

Datum: 2026-09-14. Beslut för A4 i den modulära kortplanen.

Detta dokument fastställer betydelser och acceptanskrav. Det skiljer dem från
vad som redan är verifierat i implementationen. A4 är en specifikationspunkt;
fullständig täckning, provanvändning och liveverifiering ingår i senare grindar.
Konfigurationens namn, standardvärden och versionsregler finns i
[konfigurationskontraktet](modular-configuration-contract.md).

## 1. Beslut och ursprung

Samma betydelse ska ge samma signal i timingtabell, detaljer, sektorer och diagram.
Teamaccent och grafisk stil får ändra dekorationen men aldrig datans betydelse.
Inget kritiskt tillstånd får kräva färgseende eller en laddad bild.

Kraven bygger på följande issues, lästa inklusive kommentarer 2026-09-14:

- [#404 – Colorblind support](https://github.com/Nicxe/f1_sensor/issues/404): egna
  färger och ett komplement med former; flaggans text måste kunna förklara status.
- [#530 – Lap time arrows](https://github.com/Nicxe/f1_sensor/issues/530): lägre
  varvtid visas med nedåtriktad pil, högre med uppåtriktad pil.
- [#566 – Sector timing](https://github.com/Nicxe/f1_sensor/issues/566): behåll
  föregående kompletta varv tills nästa S1 finns. Senaste sektor från olika varv
  är ett separat användarval med tydligt varvursprung.

Issuekommentarer är kravunderlag; deras tidigare releasebesked bevisar inte att
varje ny modul fungerar. Lokala källor och tester nedan beskriver nuvarande läge.

## 2. Timingstatus och prioritetsordning

| Prioritet | Status | Betydelse | Standard | Signal i nuvarande implementation |
| --- | --- | --- | --- | --- |
| 1 | Raderad | Källan har uttryckligen strukit tiden | Varning | ×, Raderad tid, överstruken tid |
| 2 | Ogiltig | Källan anger att observationen inte är giltig | Varning | ! och Ogiltig tid |
| 3 | Saknas | Ingen tolkningsbar positiv varv-/sektortid | Neutral | Tankstreck och Uppgift saknas |
| 4 | Föregående | En tid som inte är aktuell för pågående varv | Neutral | ↶ och Föregående varv samt varvnummer när känt |
| 5 | Snabbast totalt | Bekräftad bästmarkering i relevant session/del | Lila | ◆ och Snabbast totalt |
| 6 | Personbästa | Bekräftad personlig bästmarkering i relevant jämförelse | Grön | ● och Personbästa |
| 7 | Registrerad | Giltig tid utan bästmarkering | Gul | ■ och Registrerad tid |

Prioriteten ska vara deterministisk. Exempel: raderad personbästatid är raderad;
föregående varvs tidigare lila sektor visas som föregående. Den underliggande
historiken kan behålla bästflaggan men den aktuella cellens signal får inte
presentera den gamla sektorn som ett nytt rekord.

Gul betyder registrerad, inte långsammare än föregående varv. Grön betyder
personbästa, inte vunnen position. En färg får därför inte återanvändas som en
allmän signal för bra/dåligt utan en tydlig måttetikett.

◆ och ● behåller etablerad betydelse. Övriga nuvarande symboler ovan är
referensutförandet. B3/B4:s automatiska komponentprovning verifierar utförandet;
det kan fortfarande justeras efter B5/B6:s manuella användarprovning om betydelser,
texter och migration hålls intakta. Att A4 är specificerad ersätter inte den provningen.

### Tidens värde och precision

Varv-/sektortider är varaktigheter, med millisekunder. Noll, tom sträng och
felaktiga tidssträngar får inte bli en giltig varvtid. Däremot är noll giltigt
för exempelvis antal genomförda varv och återstående sessionstid.

Klockslag för sessioner och händelser följer Home Assistants tidsformat och
vald tidszon. Varaktigheter ska inte få AM/PM. Uppdateringsrader av typen
Updated in Home Assistant och automatiska leverantörsangivelser ska förbli
borttagna. Varvnummer, Q/SQ-del och jämförelsegrund är innehåll som behövs för
att förstå värdet och omfattas inte av den borttagningen.

## 3. Sektorer: samma varv eller uttryckligt blandade varv

Standard är `sectors: coherent`. Varje förare har sin egen varvsekvens;
ledarens varvnummer får inte tilldelas förare som ligger ett eller flera varv efter.

| Händelse | Förväntad visning |
| --- | --- |
| Varv 10 avslutat, varv 11 ännu utan S1 | S1/S2/S3 från varv 10, alla märkta föregående |
| Varv 11 S1 anländer | S1 från varv 11; S2/S3 saknas tills de anländer |
| Varv 11 S2 anländer | S1/S2 från varv 11; S3 saknas |
| Anslutning mitt i varvet | Visa endast observationer med känt underlag; skapa ingen tidigare historik |
| Ny session, ny kvaldel eller replay-generation | Tidigare sammanhang får inte fylla tomma sektorer |
| En sektor rättas till null | Visa saknad uppgift för den observationen; återuppliva inte den rättade tiden |
| Radering eller ogiltigmarkering | Varningsstatus har företräde över tidigare rekordstatus |

Valet `sectors: latest` får kombinera exempelvis S1 från varv 11 med S2/S3 från
varv 10. Varje gammal cell måste bära sin egen signal och sitt varvnummer.
Detta är inte en sammanhängande varvrad och får aldrig summeras till körd varvtid.
Ett saknat varvnummer får inte lånas från en annan sektor. Okänt ursprung ska
framgå; informationen får inte ges starkare säkerhet än källan medger.

Personbästa sektorer är en tredje, separat kolumnfamilj. De kan komma från olika
varv. Summan heter Teoretiskt varv och märks som en beräkning. Alla tre giltiga
sektorer måste finnas och höra till rätt sessionsdel. Kval och sprintkval får
inte summera Q1/SQ1 och Q2/SQ2 som ett gemensamt rekord.

### Sessionsregler

- Träning, race och sprint använder respektive sessions identitet och förarens
  varvnummer; en ändrad session tömmer tidigare sektorsammanhang.
- Kval och sprintkval anger Q1–Q3 respektive SQ1–SQ3. Byte av del är en gräns
  för aktuella jämförelser, även när hela sessionens identitet är oförändrad.
- Rödflagg/paus ändrar inte i sig vilket varv en redan registrerad tid kommer
  från. Banan och klockans pausstatus visas separat från timingrekord.
- Replay följer inspelningens session och position. Seek får inte blanda framtida
  observationer med tidigare varv. Samma krav gäller efter återanslutning.
- Efter avslut får sparade tider visas med sitt sammanhang. Detta får inte se ut
  som nya liveobservationer när nästa session börjar.

## 4. Pilar, delta och referenser

| Mått | Beräkning | Exempel | Text |
| --- | --- | --- | --- |
| Varvtid | aktuell tid minus referenstid | ▼ −0,245 s | Snabbare, mot varv N |
| Varvtid | aktuell tid minus referenstid | ▲ +0,245 s | Långsammare, mot varv N |
| Varvtid vid lika visad precision | avrundat delta = 0 | = 0,000 s | Oförändrat |
| Position | referensposition minus aktuell position | ↑ 2 platser | Vunnit 2 mot angiven referens |
| Position | referensposition minus aktuell position | ↓ 2 platser | Förlorat 2 mot angiven referens |
| Saknat jämförelseunderlag | ingen beräkning | — | Jämförelse saknas |

Nuvarande varvskillnad jämför två intilliggande avslutade varv som faktiskt finns
i underlaget. Om historiken hoppar från 10 till 12 visas ingen pil för 12 mot 10
under etiketten föregående varv. Ett framtida val av referensvarv ska ha en egen
uttrycklig etikett. En rättad/raderad tid får inte användas som giltig referens.

Positionens referens kan vara startuppställning eller en uttryckligt vald
observation. Den måste vara stabil och namngiven. Position 0 är inte ett giltigt
jämförelseunderlag. Positionspilar får inte användas som varvtidspilar, trots att
båda beskriver förändring. Funktionen för positionsdelta finns; det innebär inte
att alla avsedda resultattabeller redan har kolumn och editorstöd.

## 5. Flaggor, däck och identitet

| Flaggstatus | Referenssymbol | Text som alltid följer statusen |
| --- | --- | --- |
| Banan fri | ✓ | Banan fri |
| Gul | ⚑ | Gul flagg |
| Dubbel gul | ⚑⚑ | Dubbla gula flaggor |
| Röd | ⚑ | Röd flagg |
| Blå | ⚑ | Blå flagg |
| Safety Car | SC | Safety Car |
| Virtual Safety Car | VSC | Virtuell Safety Car |
| Målflagg | ▦ | Målflagg |

Flaggornas färgidentitet är skild från egna timingfärger. Gul flagg får aldrig
läsas som registrerad sektortid. En okänd flaggkod får inte bli Banan fri;
bevara texten eller visa okänd status när texten inte kan tolkas.

Compound identifieras med S/M/H/I/W och namn, aldrig bara röd/gul/vit/grön/blå.
Okänd compound får frågetecken eller sitt källnamn; den får inte bli Hard.
Bilder har reserverat utrymme, och bokstav/namn ska fungera vid bildfel och
forced colors. Teamlogo, nationalitetsflagga och evenemangsflagga är olika
identiteter. Inget av dem får ersätta förar-/teamnamn i hjälpmedlens läsordning.

Diagram som jämför förare ska ha namn plus markör eller linjemönster, även när
två förare delar teamfärg. Saknade datapunkter är luckor, inte nollor eller
påhittade interpolerade resultat. Tabellalternativet ska ha samma värden och enheter.

## 6. Anpassning och tillgänglighet

Användaren väljer symbol, text eller båda. Nuvarande `shape` visar symbol och har
statusens text för hjälpmedel; `text` visar text; `both` visar båda. Inget läge
ska göra timingstatus till enbart färg. Varvursprung ska fortsätta vara tydligt
även när den kompakta formen används.

Egna statusfärger ändrar bara paletten. Svart/vit text väljs mot den faktiska
fyllda statusbrickan. De inbyggda paletternas och testade egna färgers kontrast
kontrolleras i enhetstester. Detta bevisar inte kontrasten för samtliga tabellrader,
överlapp, fokusramar, teman och användarval; de behöver också visuell provning.

Hög kontrast, gråskala och operativsystemets forced colors ska behålla värde,
status, mått och varvursprung. Rörelse ska kunna stängas av och följa systemval.
Ingen blinkning får behövas för att förstå en flagga eller en förbättring.

Timingförklaringen ska finnas nära tabellen och vara åtkomlig med touch,
tangentbord och hjälpmedel. Nuvarande vy har en kompakt öppningsbar förklaring
med samtliga sju timingstatusar, prioritet, sektorernas valda varvläge och
varvtidspilarnas jämförelsegrund. Tangentbord, uppdateringar, egna paletter,
gråskala och smal vy med forced colors har automatiska kontroller i tre
webbläsarmotorer; bred manuell hjälpmedels- och användarprovning kvarstår i B5/B6.

## 7. Verifiering och kvarstående arbete

| Regel | Nuvarande evidens | Kvarstående verifiering |
| --- | --- | --- |
| Statusprioritet, parser, palettkontrast | `modular-semantics.test.mjs` | Alla kombinationer i faktiska teman och hjälpmedel |
| Sammanhängande/separata sektorvarv | Samma testfil, inklusive historisk practice-fixture | Helg med olika sessioner, sena starter och återanslutning |
| Null-korrigering och explicit raderat bästvarv | `modular-semantics.test.mjs`, `modular-data.test.mjs` | Raderingens väg genom alla backendkällor, retained/frozen-vyer och latest-läge |
| Teoretiskt varv och Q/SQ-delar | `modular-data.test.mjs` | Fulla sekvenser med sena korrigeringar under verkligt kval |
| Varvtids-/positionspilar | `modular-semantics.test.mjs`; timingadapter | Positionskolumner genom samtliga avsedda moduler |
| Flaggtext och däck vid bildfel | `modular.spec.js` | Användarprovning med olika färgseende och skärmläsare |
| Synligt varvursprung och legend | `view.js`, `timing-legend.spec.js`, faktisk HA-editor | Användarprovning och skärmläsarflöden |
| Session-/seek-gränser | SectorStore, kortets kontextanrop och `modular-lifecycle-matrix.md` | Verklig livehelg och flerenhetsprovning under C7/F3 |

Källor i repo:

- [Semantik och sektorlagring](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/semantics.js)
- [Timingadapter och historik](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/data.js)
- [Rendering av celler och legend](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/view.js)
- [Kortets kontext och livscykel](../custom_components/f1_sensor/www/f1-sensor-live-data-card/modular/card.js)
- [Semantiktester](../frontend-tests/unit/modular-semantics.test.mjs)
- [Datatester](../frontend-tests/unit/modular-data.test.mjs)
- [Browsertester](../frontend-tests/modular.spec.js)

A4 fastställer kontraktet ovan. B3/B4 har en sammanhållen automatiserad
komponentmatris för identitetsgrafik, timingsemantik, egna färger och färgoberoende
signaler. E4/E5 har separat sammanhållen automatiserad och runtimebaserad evidens.
B5/B6, C7 och D1/D2 kräver fortfarande bredare manuell eller verklig användning
och kan inte bockas av utifrån detta dokument eller isolerade funktionstester.
