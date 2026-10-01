# F1 Sensor – livscykelmatris för modulplattformen

Datum: 2026-09-16. Verifieringsunderlag för E5 i kortplattformens plan.

Matrisen avgränsar kortets ansvar från en verklig livehelg och flerenhetsprovning.
E5 kräver att kortet inte blandar generationer, återupplivar gammal data eller
skickar integrationsåtgärder som bieffekt när underlaget byts eller avbryts.

| Övergång | Förväntat beteende | Automatiskt bevis |
| --- | --- | --- |
| Datalucka eller tömda attribut | Behåll endast en sammanhängande sparad generation när policyn tillåter det; tillgänglig tom data ersätter tidigare rader | `retained-data.spec.js`, `modular-retained.test.mjs`, `modular-data.test.mjs` |
| Sen start eller ofullständig första observation | Ingen påhittad jämförelse, placering, varvtid eller nolla; nya giltiga värden får ta över | `modular-data.test.mjs`, `modular-session.test.mjs`, `data-time.spec.js` |
| Sessionsbyte eller avslutad session | Sparade livevärden och banväder får inte märkas om till den nya sessionen; fasstyrda moduler byter utan att skriva om konfigurationen | `retained-data.spec.js`, `data-time.spec.js`, `session-selection.spec.js` |
| Replay-seek eller byte av replay | Generationen ändras, sparad livebild ogiltigförklaras och sena telemetrisvar från föregående urval ignoreras | `modular-retained.test.mjs`, `modular-replay.test.mjs`, `modular.spec.js`, `realtime.spec.js` |
| Sent arkiv-, telemetri-, analys- eller kartsvar | Obsoleta svar får inte skriva över ny session, nytt urval eller borttaget kort | `modular.spec.js`, `realtime.spec.js`, `modular-archive.test.mjs`, `modular-connection.test.mjs` |
| Frånkoppling och återanslutning | Förklarings-/behåll-/döljpolicy visas korrekt, gamla callbacks avvisas och resurser binds till den nya anslutningsgenerationen | `data-time.spec.js`, `realtime.spec.js`, `modular-connection.test.mjs`, `modular-archive.test.mjs` |
| Entry laddas om eller tas bort | Aktiva resurser släpps; återkomst skapar nya prenumerationer utan att gammal generation publiceras | `realtime.spec.js`, `modular-connection.test.mjs` |
| Avbruten kalibrering eller sessionsslut | Sparad Live Delay behålls, körningen blir inaktiv och ett äldre försök kan inte matchas i efterhand | `calibration.spec.js`, `modular-calibration.test.mjs`, `test_calibration_behavior.py` |
| Skydd aktiveras under fryst eller sparad vy | Känslig bild tas bort och känsliga resurser stängs; lokalt Visa kan inte öppna dem | `modular.spec.js`, `data-time.spec.js`, `retained-data.spec.js`, `viewing.spec.js` |
| Kort tas bort, modul byts eller layout ändras | Frontendresurser släpps utan att stoppa backend-replay eller skriva till automationer | `modular.spec.js`, `realtime.spec.js`, `modular-connection.test.mjs` |

Proven körs i Chromium och de 154 icke-snapshotbaserade flödena körs även i
Firefox och WebKit. En tidigare verifierad HAdev-omstart visade verklig
frånkoppling, återanslutning och återkomst av data utan att kortinställningar
ändrades. Den katalogdrivna skyddsmatrisen täcker alla känsliga modulresurser.

Detta stänger E5 för den implementerade frontend-/backendgränsen. Det ersätter
inte en verklig livehelg, långvarig belastning eller samtidiga verkliga klienter.
Dessa ligger kvar under C7, D2 och F3.
