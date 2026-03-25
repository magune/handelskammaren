Regelverk 2 - Operativt verifieringsregelverk för Certificate of Origin
Tillåten normalisering (central regel)
Inför jämförelse får systemet normalisera:
- versaler och gemener
- radbrytningar
- extra mellanslag
- vanliga företagsbeteckningar (AB, Ltd, GmbH, SARL, BV, Inc.)
- symboler såsom & och AND
- punktnotation och vedertagna förkortningar

Adressnormalisering får tillämpas när det endast gäller gatutyp:
- gata / gatan
- väg / vägen
- street / st
- road / rd

Normalisering får endast ske enligt uttryckliga regler i detta regelverk.
Semantisk tolkning eller sannolikhetsbedömning får inte användas.

1. Bakgrund och syfte
Detta dokument reglerar en AI-baserad förhandsgranskning av ansökningar om Certificate of Origin (COO). Systemet ska automatiskt jämföra uppgifterna i certifikatet med uppgifterna i den bifogade fakturan och verifiera att de överensstämmer. Systemet fattar inte myndighetsbeslut utan levererar ett granskningsresultat till Certiataplus.
2. Övergripande principer
Verifieringen är ensidig: uppgifter i certifikatet ska kunna styrkas mot fakturan.
Systemet ska inte granska fakturan utöver vad som krävs för att verifiera certifikatets uppgifter.
Vid avvikelse, saknad uppgift eller osäkerhet ska ärendet skickas till manuell handläggning.
Systemet ska vara strikt och konservativt och får inte fatta automatiska godkännanden vid tveksamhet.

2.1 Grundläggande verifieringsprincip
Verifieringen i samtliga kontrollpunkter ska vara ensidig.
Systemet ska enbart kontrollera att de uppgifter som anges i certifikatet kan identifieras i den bifogade fakturan.
Systemet ska inte analysera fakturan i sin helhet och ska inte identifiera eller bedöma uppgifter som inte uttryckligen anges i certifikatet.
Förekomst av ytterligare information i fakturan som inte motsvarar en uppgift i certifikatet ska därför inte i sig medföra MISMATCH.
Systemet ska endast verifiera de uppgifter som anges i respektive kontrollpunkt.
Automatiskt godkännande får endast ske när uppgifterna i certifikatet tydligt och utan tolkning kan verifieras mot fakturan.
2.2 Särskilt undantag – Letter of Credit (LC)
Rättslig företrädesordning
Denna bestämmelse har företräde framför samtliga kontrollpunkter i avsnitt 4.
När denna bestämmelse är tillämplig ska verifieringen ske uteslutande enligt nedanstående regler, oavsett vad som anges i avsnitt 4.1–4.5.
Tillämpning
Undantaget ska tillämpas när certifikatet innehåller en uttrycklig hänvisning till ett specifikt och individuellt LC-nummer (Letter of Credit).
Systemet ska identifiera benämningar såsom exempelvis:
LC
L/C
Letter of Credit
Documentary Credit
LC No.
LC Number
Undantaget ska endast aktiveras när ett konkret nummer anges i direkt anslutning till LC-hänvisningen.
Verifieringens omfattning vid LC
Vid tillämpning av denna bestämmelse ska systemet enbart verifiera ursprungsland enligt avsnitt 4.5.
Systemet ska då:
– verifiera att varje ursprungsland som anges i certifikatet återfinns explicit i fakturan efter normalisering,
– tillämpa normalisering enligt avsnitt 4.5.
Systemet ska inte verifiera:
– varubeskrivning,
– kvantitet/mängd,
– avsändare (Consignor),
– mottagare (Consignee),
– leveransvillkor,
– andra uppgifter.
Avvikelse
Om ursprungsland inte entydigt kan identifieras i fakturan ska ärendet skickas till manuell handläggning.
3. Språk
Systemet ska kunna hantera uppgifter oavsett språk.
Fakturan och certifikatet behöver inte vara upprättade på samma språk.
Certifikatet ska vara huvudsakligen skrivet på ett och samma språk.
Förekomst av enstaka ord, egennamn eller standardiserade tvåspråkiga rubriker ska inte i sig medföra avvikelse.
Om språklig blandning påverkar möjligheten att verifiera uppgifter ska ärendet skickas till manuell handläggning.

4. Kontrollpunkter:
4.1 Kontrollpunkt: Avsändare (Consignor)
Syfte
Systemet ska verifiera att den avsändare som anges i certifikatet kan styrkas mot uppgifter i den bifogade fakturan.
Verifieringen är ensidig:
Uppgiften i certifikatet ska kunna återfinnas i fakturan.
Systemet ska inte göra antaganden om koncernrelationer, agentförhållanden eller handelsrelationer utöver vad som uttryckligen framgår av fakturan.

Särskild regel – Koncernstruktur
Consignor får avvika från fakturans “From”-fält om företagsnamnet uttryckligen förekommer i fakturans header-, VAT-, postal- eller treasury-/bankblock.
Företagsnamnet ska vara exakt identifierbart i fakturan.
Om consignor inte kan återfinnas uttryckligen någonstans i fakturan → MISMATCH.
Ingen tolkning av koncernrelationer eller antagande om ägarförhållanden får göras

4.1.1 Identifiering i fakturan
Systemet ska identifiera uppgifter om fakturautställaren eller annan möjlig avsändarpart i fakturan.
Relevanta benämningar kan exempelvis vara:
Seller, Exporter, Consignor, Shipper, Supplier, Manufacturer, Vendor, Buyer, Delivery address, Ship to, Notify party eller motsvarande.
Om särskild rubrik saknas ska systemet utgå från den part som har utfärdat fakturan (fakturautställaren), normalt angiven i dokumentets sidhuvud eller genom företagsuppgifter kopplade till fakturan.

4.1.2 Verifiering av avsändare
Systemet ska verifiera att avsändarens företagsnamn och land som anges i certifikatet kan identifieras i fakturan.
Verifieringen ska avse samma juridiska part.

4.1.3 Normalisering inför jämförelse
Reglerna i avsnitt 4.1.3.1–4.1.3.6 ska prövas sekventiellt.
Om en bestämmelse inte är tillämplig eller dess villkor inte är uppfyllda ska systemet fortsätta pröva nästa bestämmelse innan MISMATCH fastställs.
Denna prövningsordning utgör undantag från huvudregeln i punkt 4.1.4 när villkoren i senare bestämmelser är uppfyllda.
Inför jämförelse får systemet normalisera:
• versaler/gemener
• radbrytningar
• extra mellanslag
• vanliga företagsbeteckningar (t.ex. AB, Ltd, GmbH, SARL, BV, Inc.)
• & och AND
• punktnotation och vanliga förkortningar
Smärre variationer i formatering ska inte medföra avvikelse.
Exempel på tillåten variation i adressuppgifter
postbox istället för gatuadress
annan ordningsföljd på adressuppgifter
mindre stavningsvariationer
olika postnummerformat

4.1.3.1 Förtydligande – Juridisk part
Företagsnamnet i certifikatet ska kunna identifieras i fakturan som samma juridiska part.
Om certifikatet anger ett annat bolagsnamn än det som framgår som fakturautställare i fakturan ska resultatet vara MISMATCH, om inte samma juridiska namn tydligt kan identifieras i fakturan.
Systemet får inte:
anta koncernrelation
anta moder-/dotterbolagsförhållande
anta agent- eller tradingrelation
göra semantisk tolkning av bolagsidentitet

4.1.3.2 Särskilt förtydligande – Avkortning av företagsnamn
Avkortning av företagsnamn i fakturan får accepteras endast när samtliga nedanstående villkor är uppfyllda:
– Den avkortade texten i fakturan utgör en exakt inledande del av företagsnamnet i certifikatet.
– Avkortningen sker i slutet av ord och beror uppenbart på layout- eller fältbegränsning.
– Ingen annan juridisk part med motsvarande namnstruktur kan identifieras i fakturan.
– Ingen ytterligare uppgift i fakturan motsäger att det rör sig om samma juridiska part.
– Landuppgiften överensstämmer enligt punkt 4.1.4.
Systemet får inte komplettera, korrigera eller rekonstruera företagsnamn annat än enligt ovanstående strikt definierade förutsättningar.
Om något av villkoren inte är uppfyllt ska resultatet vara MISMATCH.

4.1.3.3 Särskilt förtydligande – Kommersiell förkortning av företagsnamn
Denna bestämmelse avser inte layout- eller fältbegränsad avkortning enligt punkt 4.1.3.2, utan språkligt vedertagen förkortning av ord i det juridiska företagsnamnet.
En kommersiell förkortning av företagsnamn i certifikat eller faktura får accepteras när samtliga nedanstående villkor är uppfyllda:
– Den förkortade formen består av tydliga och vedertagna förkortningar av ord i det fullständiga juridiska namnet.
– Det fullständiga juridiska företagsnamnet framgår uttryckligen i fakturan.
– Ingen annan juridisk part med liknande namnstruktur förekommer i dokumentet.
– Adressuppgifter och land överensstämmer enligt punkt 4.1.4.
– Inga uppgifter i fakturan motsäger att det rör sig om samma juridiska part.
Systemet får inte anta koncernrelation, ägarförhållande eller göra fri språklig tolkning.
Om ovanstående villkor inte är uppfyllda ska resultatet vara MISMATCH.

4.1.3.4 Särskilt undantag – Kommersiellt namn / registrerat bolagsnamn
Skillnad mellan kommersiellt namn (t.ex. varumärke eller affärsnamn) och registrerat juridiskt bolagsnamn får accepteras endast när samtliga nedanstående villkor är uppfyllda:
– Postadress (gata eller box) och postnummer överensstämmer exakt mellan certifikat och faktura.
– Land är identiskt enligt punkt 4.1.4
– Det registrerade bolagsnamnet (juridisk part) framgår uttryckligen i fakturan.
– Ingen annan juridisk part med liknande namn förekommer i fakturan.
– VAT-nummer, organisationsnummer eller annan företagsidentifierare i fakturan motsäger inte att det rör sig om samma juridiska part.
Systemet får inte anta koncernrelation, varumärkesägarskap eller handelsrelation utan uttrycklig identifiering i fakturan.
Om något av ovanstående villkor inte är uppfyllt ska resultatet vara MISMATCH.

4.1.3.4.1 Förtydligande – ändrat eller alternativt registrerat bolagsnamn
Skillnad mellan två registrerade bolagsnamn får accepteras när samtliga följande villkor är uppfyllda:
– Postadress (gata eller box) och postnummer överensstämmer exakt mellan certifikat och faktura.
– Land är identiskt enligt punkt 4.1.4.
– Organisationsnummer, VAT-nummer eller annan företagsidentifierare i fakturan motsäger inte att det rör sig om samma juridiska part.
– Ingen annan juridisk part med liknande namnstruktur förekommer i fakturan.
Systemet får inte anta koncernrelation eller ägarförhållande.
Om ovanstående villkor inte är uppfyllda ska resultatet vara MISMATCH.

4.1.3.5 Särskilt förtydligande – Utelämnade generiska organisationsord
Skillnader mellan företagsnamn som enbart består av att generiska organisationsord har utelämnats eller lagts till får accepteras när samtliga nedanstående villkor är uppfyllda:
– Företagsnamnets huvuddel (core name) är identisk i certifikat och faktura.
– Skillnaden består endast av tillägg eller utelämnande av generiska organisationsord som inte ändrar företagets identitet.
– Exempel på sådana organisationsord är: Products, Group, Company, Corporation, Industries, Systems, Solutions eller motsvarande.
– Ingen annan juridisk part med motsvarande namnstruktur förekommer i fakturan.
– Adressuppgifter och land överensstämmer enligt punkt 4.1.4
– Inga uppgifter i fakturan motsäger att det rör sig om samma juridiska part.
Systemet får inte anta koncernrelation, ägarförhållande eller göra fri språklig tolkning av företagsidentitet.
Om ovanstående villkor inte är uppfyllda ska resultatet vara MISMATCH.

4.1.3.6 Förkortning av juridisk bolagsform
Skillnader som enbart avser förkortning eller fullständig skrivning av juridisk bolagsform får accepteras.
Exempel:
AG ↔ Aktiengesellschaft
Ltd ↔ Limited
SA ↔ Sociedad Anónima / Société Anonyme
GmbH ↔ Gesellschaft mit beschränkter Haftung
BV ↔ Besloten Vennootschap
förutsatt att:
– företagsnamnets huvuddel är identisk
– ingen annan juridisk part med motsvarande namnstruktur förekommer i fakturan
– adressuppgifter och land överensstämmer enligt punkt 4.1.4
Om ovanstående villkor inte är uppfyllda ska resultatet vara MISMATCH.

4.1.4 Land
Land som anges för avsändaren i certifikatet ska överensstämma exakt med det land som anges för motsvarande part i fakturan efter normalisering av landsnamn.
Om land inte överensstämmer ska resultatet vara MISMATCH.

4.1.5 MATCH / MISMATCH
MATCH föreligger när:
företagsnamnet i certifikatet kan identifieras som samma juridiska part i fakturan, och
land överensstämmer efter normalisering.
MISMATCH föreligger när:
avsändaren inte kan identifieras i fakturan,
annat bolagsnamn anges utan entydig koppling,
land inte överensstämmer, eller
uppgifterna inte entydigt kan kopplas till samma juridiska part.

4.2 Kontrollpunkt: Mottagare (Consignee)
Syfte
Systemet ska verifiera att den mottagare som anges i certifikatet kan styrkas mot uppgifter i den bifogade fakturan.
Verifieringen är ensidig: Uppgiften i certifikatet ska kunna återfinnas i fakturan.
Systemet ska inte göra antaganden om koncernrelationer, agentförhållanden eller handelsrelationer utöver vad som uttryckligen framgår av fakturan.
Normaliseringsregler enligt punkt 4.1.3.1–4.1.3.6 i kontrollpunkten Avsändare ska tillämpas även vid verifiering av mottagare.
Grundregel
Consignee ska normalt motsvara fakturans “Invoice to”, “Bill to”, “Sold to” eller “Ship to”.
Särskilda regler
– Koncernstruktur
Consignee får avvika från ovanstående fält om företagsnamnet uttryckligen förekommer i fakturans sidhuvud eller i adress-/identifieringsblock (t.ex. VAT-block).
– Dealer / leveransmottagare
Consignee får även motsvara företagsnamn som uttryckligen förekommer i något av följande fält/avsnitt i fakturan:
Delivery address
Receiver
Dealer
Importer / Importer ref
Consignee (om fakturan själv har ett sådant fält)
Företagsnamnet ska vara exakt identifierbart i fakturatexten. Ingen tolkning av koncernrelationer, förkortningar eller handelsnamn får göras.
Om consignee inte kan återfinnas uttryckligen i något av ovanstående fält/avsnitt → MISMATCH.
Formulärets nederkant
4.2.1 Identifiering i fakturan
Systemet ska identifiera uppgifter om mottagande part i fakturan.
Relevanta benämningar kan exempelvis vara:
Buyer
Sold To
Consignee
Ship To
Delivery Address
Notify Party
Importer
eller motsvarande.
Om flera parter anges i fakturan ska systemet kontrollera samtliga relevanta mottagarroller.
4.2.1.1 Förtydligande – alternativ mottagaradress
Om den mottagare som anges i certifikatet inte återfinns under fakturans fält Consignee får systemet identifiera mottagaren i andra adressfält i fakturan enligt punkt 4.2.1.
Om en speditör, transportör eller logistikleverantör anges som Consignee i fakturan ska detta i sig inte medföra MISMATCH, förutsatt att mottagaren som anges i certifikatet kan identifieras i något annat adressfält i fakturan.
Om mottagaren i certifikatet återfinns under exempelvis Delivery Address, Ship To eller Notify Party ska detta accepteras, förutsatt att:
– samma juridiska part kan identifieras, och
– ingen annan uppgift i fakturan motsäger att det rör sig om samma mottagare.
Om mottagaren i certifikatet inte kan identifieras i något adressfält i fakturan ska resultatet vara MISMATCH.

4.2.2 Verifiering av mottagare
Företagsnamnet som anges som mottagare i certifikatet ska kunna identifieras i fakturan efter tillåten normalisering.
Mottagaren i certifikatet behöver inte vara identisk med fakturans köpare (Buyer/Sold To), under förutsättning att den kan återfinnas i fakturan i annan tydligt angiven mottagar- eller leveransroll.
Om mottagaren i certifikatet inte kan identifieras någonstans i fakturan ska resultatet vara MISMATCH.
4.2.2.1 Normalisering inför jämförelse
Inför jämförelse får systemet normalisera:
versaler/gemener
radbrytningar
extra mellanslag
vanliga företagsbeteckningar (AB, Ltd, LLC, GmbH, SARL, BV, Inc. m.fl.)
& och AND
punktnotation och vanliga förkortningar
Smärre variationer i formatering ska inte medföra avvikelse.
Adressuppgifter får vara mer eller mindre fullständiga än i fakturan, förutsatt att:
ingen motsägelse förekommer, och
uppgifterna entydigt avser samma juridiska part.

4.2.2.1.1 Särskilt förtydligande – avkortning av företagsnamn till följd av layout- eller fältbegränsning
Avkortning av företagsnamn i fakturan får accepteras endast när samtliga nedanstående villkor är uppfyllda:
Den avkortade texten i fakturan utgör en exakt inledande del (prefix) av företagsnamnet i certifikatet.
Avkortningen sker i slutet av ord och beror uppenbart på layout- eller fältbegränsning.
Ingen annan juridisk part med motsvarande namnstruktur kan identifieras i fakturan.
Ingen ytterligare text i fakturan motsäger att det rör sig om samma juridiska part.
Landuppgiften överensstämmer enligt punkt 4.2.3
Systemet får inte komplettera, korrigera eller rekonstruera företagsnamn annat än enligt ovanstående strikt definierade förutsättningar.
Om något av villkoren inte är uppfyllt ska resultatet vara MISMATCH.

4.2.2.1.2 Särskilt förtydligande – Kommersiell förkortning av företagsnamn
En kommersiell förkortning av företagsnamn i certifikat eller faktura får accepteras när samtliga nedanstående villkor är uppfyllda:
– Den förkortade formen består av tydliga och vedertagna förkortningar av ord i det fullständiga juridiska namnet.
– Det fullständiga juridiska företagsnamnet framgår uttryckligen i fakturan.
– Ingen annan juridisk part med liknande namnstruktur förekommer i dokumentet.
– Adressuppgifter och land överensstämmer enligt punkt 4.2.3.
– Inga uppgifter i fakturan motsäger att det rör sig om samma juridiska part.
Systemet får inte anta koncernrelation, ägarförhållande eller göra fri språklig tolkning.
Om ovanstående villkor inte är uppfyllda ska resultatet vara MISMATCH.
4.2.2.2 Särskilt undantag – Consignee angiven som “To order”
Om mottagaren i certifikatet anges som “To order” får avsaknad av företagsnamn accepteras.
I sådant fall ska verifieringen begränsas till att kontrollera att det land som anges i certifikatet för mottagaren kan identifieras i fakturan.
Följande gäller:
– uttrycket “To order” i certifikatet ska inte i sig medföra MISMATCH
– något företagsnamn behöver inte verifieras mot fakturan
– landet som anges i certifikatet ska kunna identifieras i fakturan enligt punkt 4.2.3
Systemet får inte:
– anta vilket företag som avses med “To order”
– komplettera med företagsnamn från fakturan
– göra semantisk tolkning av mottagaridentitet

4.2.3 Land
Land som anges för mottagaren i certifikatet ska överensstämma med det land som anges för motsvarande part i fakturan efter normalisering av landsnamn.
Om land inte överensstämmer ska resultatet vara MISMATCH.
4.2.4 MATCH / MISMATCH
MATCH föreligger när:
mottagarens företagsnamn kan identifieras i fakturan, och
land överensstämmer efter normalisering.
MISMATCH föreligger när:
mottagaren inte kan identifieras i fakturan,
annat bolagsnamn anges utan att kunna återfinnas i fakturan,
land inte överensstämmer, eller
uppgifterna inte entydigt kan kopplas till samma juridiska part.

4.3 Kontrollpunkt: Varubeskrivning
Syfte
Systemet ska verifiera att den varubeskrivning som anges i certifikatet kan styrkas mot den bifogade fakturan.
Verifieringen är ensidig:
Uppgiften i certifikatet ska kunna återfinnas i fakturan.
Systemet får inte göra semantisk tolkning eller sannolikhetsbedömning.

4.3.1 Identifiering i fakturan
Systemet ska identifiera relevant varubeskrivning i fakturan.
Om flera varor förekommer ska systemet säkerställa att varje vara i certifikatet kan återfinnas i fakturan.
4.3.2 Artikelnummer – primär verifieringsgrund
Om artikelnummer anges i både certifikat och faktura ska matchning primärt ske via artikelnummer.
Artikelnumret i certifikatet ska exakt kunna identifieras i fakturan efter tillåten normalisering.
Om artikelnummer inte överensstämmer ska resultatet vara MISMATCH.

4.3.3 Specifik varubeskrivning – kontrollerad textmatchning
Om artikelnummer inte används ska verifiering ske genom kontrollerad textmatchning.
Inför jämförelse får systemet normalisera:
– versaler/gemener
– radbrytningar
– extra mellanslag
– bindestreck
Efter sådan normalisering ska certifikatets identitetsbärande huvudbeteckning kunna identifieras i fakturans varubeskrivning.
Systemet ska identifiera den produktbeteckning som bär produktens identitet (identitetsbärande huvudbeteckning) utan att använda semantisk tolkning, synonymi eller branschmässiga antaganden.
Den identitetsbärande huvudbeteckningen ska identifieras som den sammanhängande ordsekvens i certifikatets varubeskrivning som tydligast identifierar produkten som en unik vara. Vid identifiering ska systemet utgå från den exakta ordsekvens som förekommer i certifikatet utan att omformulera eller tolka betydelsen.
Matchning ska baseras på denna identitetsbärande huvudbeteckning. Eventuella tillägg före eller efter huvudbeteckningen ska hanteras enligt punkt 4.3.4.
Matchning får inte baseras på:
– synonymi
– omformulering
– ändrad ordningsföljd av den identitetsbärande huvudbeteckningen
– uppdelning eller sammanslagning av sifferkombinationer
– branschmässig tolkning
Om den identitetsbärande huvudbeteckningen i certifikatet inte kan identifieras i fakturan ska resultatet vara MISMATCH.
 

4.3.4 Förtydligande – Tillägg som inte påverkar produktidentitet
Vid kontrollerad textmatchning enligt punkt 4.3.3 ska systemet identifiera produktens identitetsbärande huvudbeteckning.
Om certifikatet eller fakturan innehåller ytterligare tillägg före eller efter huvudbeteckningen ska sådana tillägg inte i sig medföra MISMATCH när följande villkor är uppfyllda:
– den identitetsbärande huvudbeteckningen kan identifieras exakt i båda dokumenten efter tillåten normalisering
– tillägget inte ändrar produktens modell, variant, kvalitet, artikelidentitet eller försäljningsenhet
– ingen annan produkt med liknande beteckning förekommer i fakturan på ett sätt som skapar oklarhet
Tilläggen får exempelvis avse:
– interna referenser
– artikel- eller identifieringskoder (t.ex. EAN, REF, ITEM, CODE)
– förpackningsangivelse
– partimarkeringar
– landsbeteckningar (SE, EU)
Sådana tillägg ska betraktas som icke identitetsbärande text.
Den identitetsbärande huvudbeteckningen ska dock kunna identifieras exakt i fakturan efter tillåten normalisering. Förekomst av icke identitetsbärande tillägg före eller efter huvudbeteckningen ska inte i sig medföra MISMATCH.
Om huvudbeteckningen inte kan identifieras enligt ovan ska resultatet vara MISMATCH.
 
Varför detta löser problemet

4.3.5 Generell varubeskrivning med fakturareferens
Certifikatet får innehålla en generell varubeskrivning under förutsättning att certifikatet samtidigt anger:
– fakturanummer, ordernummer eller orderreferens, och
– fakturadatum.
Certifikatet ska dessutom innehålla en uttrycklig hänvisning till fakturan, exempelvis formuleringar såsom:
– “according to attached invoice”
– “as per invoice”
– “see attached invoice”
– eller motsvarande uttryck.
Systemet ska verifiera att:
– den referens som anges i certifikatet (fakturanummer, ordernummer eller orderreferens) exakt överensstämmer med motsvarande uppgift i fakturan
Vid normalisering av datum får systemet acceptera olika standardiserade datumformat, exempelvis:
– YYYY-MM-DD
– DD/MM/YYYY
– DD/MM/YY
– MM/DD/YYYY
om dessa entydigt representerar samma kalenderdatum.
Om dessa uppgifter överensstämmer ska varubeskrivningen anses verifierad utan ytterligare textmatchning, förutsatt att artikelnummer kontrolleras enligt punkt 4.3.2 när sådana anges i certifikatet.
Om referensnummer, datum eller uttrycklig fakturahänvisning saknas eller inte överensstämmer ska resultatet vara MISMATCH.

4.3.6 Förtydligande – Artikelnummer
Om certifikatet innehåller artikelnummer ska dessa kunna identifieras exakt i fakturan.
Artikelnummer ska jämföras som exakta identifierare.
Systemet får inte använda semantisk eller approximativ matchning av artikelnummer.
Om artikelnummer i certifikatet inte kan identifieras i fakturan ska resultatet vara MISMATCH.

4.3.7 Förtydligande – Koppling mellan vara och ursprungsland vid flera ursprung
När certifikatet innehåller mer än ett ursprungsland och varorna anges separat i certifikatet (per artikelrad eller motsvarande uppdelning) ska det entydigt framgå vilket ursprungsland som avser respektive vara.
Detta krav anses uppfyllt när:
– ursprungsland anges direkt efter respektive artikel i certifikatet, eller
– certifikatet innehåller en uttrycklig hänvisning till fakturan i varubeskrivningen (t.ex. “according to attached invoice”, “as per invoice” eller motsvarande).
Om certifikatet innehåller flera ursprungsländer men inte anger ursprung per artikel och inte heller innehåller en sådan fakturahänvisning ska resultatet vara MISMATCH.
Denna bestämmelse gäller endast när certifikatet innehåller flera ursprungsländer.
När certifikatet anger ett enda ursprungsland krävs ingen sådan koppling per artikel.




4.3.8 MATCH / MISMATCH
MATCH föreligger när varubeskrivningen kan verifieras enligt punkt 4.3.1–4.3.5 och, när artikelnummer anges i certifikatet, enligt punkt 4.3.2.
MISMATCH föreligger när:
– varubeskrivningen inte kan verifieras utan tolkning eller semantisk jämförelse,
– fakturareferens, datum eller uttrycklig fakturahänvisning saknas eller inte överensstämmer enligt punkt 4.3.5, eller
– artikelnummer som anges i certifikatet inte kan identifieras exakt i fakturan enligt punkt 4.3.2.

4.4 Kontrollpunkt: Kvantitet / Mängd
Syfte
Systemet ska verifiera att den kvantitet eller mängd som anges i certifikatet återfinns i den bifogade fakturan.
Verifieringen ska i första hand baseras på identifiering av motsvarande uppgift i fakturan.
I de fall där detta inte är möjligt får systemet använda de beräkningsmetoder som uttryckligen tillåts i detta regelverk (avsnitt 4.4.5.2–4.4.5.6), såsom summering av artikelrader eller enhetsomräkning. 
Systemet får inte göra tolkning, summering eller omräkning utöver de beräkningsmetoder som uttryckligen tillåts i detta regelverk (4.4.5.2–4.4.5.6).
– summering av flera fakturor
– enhetsomräkning
– härledning av styckvikt
– summering av flera artikelrader

4.4.1 Förekomstkontroll
Systemet ska verifiera att den kvantitet eller mängd som anges i certifikatet kan identifieras i den bifogade fakturan.
Verifieringen ska ske genom kontroll av att det numeriska värdet som anges i certifikatet kan identifieras i fakturan.
Systemet ska inte göra tolkning, uppskattning eller semantisk jämförelse av kvantiteter utöver vad som uttryckligen anges i detta avsnitt.

4.4.2 Krav på kvantitetsuppgift i certifikatet
När kvantitet anges i certifikatet ska både:
– numeriskt värde, och
– kvantitetsenhet
framgå uttryckligen i samma uppgift.
Exempel på kvantitetsenheter kan vara exempelvis:
PCS
PC
UNITS
SETS
KG
MT
BOXES
PACKAGES
eller motsvarande.
Om certifikatet anger en numerisk kvantitet utan uttrycklig enhet ska resultatet vara MISMATCH
4.4.2.1 Förtydligande – flera kvantitetsuppgifter i certifikatet
Om flera olika kvantitetsuppgifter förekommer i certifikatet ska verifieringen utgå uteslutande från den kvantitetsuppgift som är placerad i fältet “Quantity / Mängd”.
Övriga uppgifter i varubeskrivningen eller i andra delar av certifikatet ska inte behandlas som den verifieringsgrundande kvantiteten om de inte uttryckligen anges i kvantitetsfältet.

4.4.2.2 Särskilt krav – viktangivelse
När kvantitet i certifikatet anges i viktenhet ska även viktkategori framgå uttryckligen.
Viktkategori ska anges som exempelvis:
– Gross Weight (GW)
– Net Weight (NW)
– Gross
– Net
eller motsvarande uttryck.
Om certifikatet anger en viktenhet utan att viktkategori uttryckligen anges ska resultatet vara MISMATCH.
Viktkategori får inte fastställas genom tolkning mot fakturan.

4.4.3 Verifiering mot faktura
Vid verifiering ska systemet kontrollera att det numeriska värdet som anges i certifikatet kan identifieras i fakturan.
Verifieringen avser enbart det numeriska värdet.
Fakturan behöver inte ange samma kvantitetsenhet som certifikatet.
Det är tillräckligt att det numeriska värdet i certifikatet kan identifieras i fakturan för motsvarande vara eller försändning.
Endast kontroll av att samma numeriska värde kan identifieras i fakturan ska utföras, med undantag för de uttryckliga undantag som anges i avsnitt 3A, 3B, 3C, 3D och 3E

4.4.3.1 Flera kvantitetsuppgifter i certifikatet
När flera kvantitetsuppgifter förekommer i certifikatet ska systemet verifiera minst en av dessa kvantitetsuppgifter mot fakturan enligt reglerna i punkt 4.4.3
Systemet ska inte kräva att samtliga kvantitetsuppgifter verifieras mot fakturan.
Övriga kvantitetsuppgifter i certifikatet ska inte i sig medföra MISMATCH om:
de inte kan verifieras mot fakturan, och
ingen uppgift i fakturan uttryckligen motsäger dessa kvantitetsuppgifter.
Om fakturan innehåller en kvantitetsuppgift som uttryckligen motsäger en kvantitet som anges i certifikatet ska resultatet vara MISMATCH.
Om osäkerhet uppstår om kvantitetsuppgifternas inbördes relation ska ärendet skickas till manuell handläggning.

4.4.3.2 Förtydligande – Kvantitet som avser försändelse eller kolli
När certifikatet anger kvantitet i form av en uppgift som avser hela försändelsen eller ett kolli, exempelvis:
“1 package”
“1 shipment”
“1 consignment”
“1 lot”
“1 lot of goods”
“1 set”
ska denna uppgift anses verifierad även om motsvarande kvantitet inte uttryckligen framgår i fakturan per artikelrad.
I sådana fall ska systemet verifiera att:
– certifikatet innehåller en verifierbar fakturareferens enligt kontrollpunkten Varubeskrivning – generell varubeskrivning med fakturareferens, och
– fakturan innehåller en varuspecifikation som entydigt motsvarar den försändning som certifikatet hänvisar till.
Systemet ska inte försöka härleda eller summera artikelkvantiteter i fakturan för att verifiera denna typ av kvantitetsuppgift.

4.4.3.3 Förtydligande – Tillåten normalisering av talformat (tusentalsavskiljare)
Vid verifiering av kvantitet får systemet normalisera numeriska värden genom att ta bort tusentalsavskiljare när följande villkor är uppfyllda:
• den kvantitet som jämförs avser samma vara eller artikelrad
• båda värdena är heltal (ingen decimaldel)
• avskiljaren förekommer endast som tusentalsavskiljare
Tillåtna tusentalsavskiljare som får tas bort är:
punkt (.)
mellanslag ( )
hårt mellanslag.
Exempel:
1599 MM i certifikatet får identifieras i fakturan som 1.599 MM eller 1 599 MM efter normalisering.
Om fakturan eller certifikatet innehåller decimaldel (t.ex. 1.599,5 eller 1599,5) får normalisering enligt denna punkt inte användas.
Kvantiteten ska då kunna identifieras enligt punkt 4.4.3
Om detta inte är möjligt ska resultatet vara MISMATCH.
Normalisering enligt denna punkt får endast användas när det är entydigt att avskiljaren fungerar som tusentalsavskiljare och inte som decimaltecken.
4.4.4 Förtydligande – Total vikt i faktura
När certifikatet anger vikt för hela försändelsen (t.ex. Gross Weight eller Net Weight) får denna uppgift verifieras mot en total vikt som anges i fakturan, exempelvis:
– “Total Weight”
– “Total Gross Weight”
– “Total Net Weight”
– “Weight”
förutsatt att:
– det numeriska värdet och viktenheten överensstämmer, och
– uppgiften entydigt avser den aktuella fakturan eller försändningen.
Skillnad i benämning mellan viktkategori i certifikatet och fakturan ska i sig inte medföra MISMATCH när det numeriska värdet och viktenheten överensstämmer.
När vikt anges i certifikatet ska både numeriskt värde och måttenhet framgå uttryckligen i samma fält.
Om GW, NW, Gross eller Net anges ska även viktenheten (t.ex. KG, MT, LB) anges uttryckligen.
Angivelse av enbart numeriskt värde tillsammans med GW/NW utan uttrycklig enhet ska klassificeras som MISMATCH.
Enheten får inte fastställas genom tolkning mot fakturan.

4.4.5 Ingen summering eller beräkning
Systemet får inte:
summera radposter
räkna om vikter
konvertera mellan enheter (med undantag för avsnitt 3B)
göra proportionella beräkningar
Uppgiften ska uttryckligen kunna identifieras i fakturan.
Undantag från denna huvudregel gäller endast enligt avsnitt 3A, 3B, 3C, 3D och 3E.


4.4.5.1 Tillämpningsordning för undantag
När verifiering enligt huvudregeln i punkt 4.4.1–4.4.2 inte kan genomföras ska systemet pröva de särskilda undantagen i följande ordning:
Summering av flera fakturor (3A)
Enhetsomräkning mellan MT och KG (3B)
Härledning av styckvikt (3C)
Summering av flera rader inom samma faktura (3D)
Summering av radvikter när totalrad saknas (3E)
Systemet ska pröva undantagen sekventiellt i angiven ordning.
Om villkoren i ett undantag inte är uppfyllda ska systemet fortsätta pröva nästa undantag innan MISMATCH fastställs.
Endast ett undantag får tillämpas vid verifieringen.  
Regler från olika undantag får inte kombineras.
4.4.5.2 Särskilt undantag – Summering av flera fakturor
Systemet får summera total vikt från flera fakturor endast när samtliga nedanstående villkor är uppfyllda.

4.4.5.2.1 Fakturareferenser i certifikatet

Certifikatet ska alltid uttryckligen ange den totala kvantiteten eller kvantitet per artikel.
Kvantitet får inte anges enbart genom hänvisning till faktura.
Om certifikatet saknar uttrycklig numerisk kvantitet → MISMATCH.
När flera fakturor ingår ska samtliga vara bifogade för att summering enligt 3A ska kunna verifieras.

4.4.5.2.2 Typ av vikt
Certifikatet ska uttryckligen ange viktkategori:
– Gross Weight (GW), och/eller
– Net Weight (NW).
Viktenheten (t.ex. KG eller MT) ska vara uttryckligen angiven.
Kombinerad viktkategori får accepteras endast om villkoren enligt punkt 2 är uppfyllda.
Summering får endast ske per viktkategori:
– GW jämförs uteslutande mot summan av “Total Gross Weight …” från respektive faktura.
– NW jämförs uteslutande mot summan av “Total Net Weight …” från respektive faktura.
Endast fakturornas uttryckliga totalrader får användas.
Om någon faktura saknar totalrad för relevant vikt → MISMATCH.

4.4.5.2.3 Enhet
Endast vikter angivna i KG eller konverterade till KG enligt avsnitt 3B får summeras.
Om någon faktura anger annan enhet eller om vikten endast framgår per rad → MISMATCH.
(Detta påverkar inte tillämpning enligt avsnitt 3C.)
Ingen annan omräkning mellan enheter än enligt avsnitt 3B får ske.

4.4.5.2.4 Tolerans
Tolerans (±0,1 % eller ±0,001 av angiven enhet) tillämpas på den sammanlagda totalsumman.

4.4.5.2.5 Avgränsning
Summering får endast ske när fler än en faktura ingår i ärendet och dessa tillsammans styrker den kvantitet som uttryckligen anges i certifikatet.
Om endast en faktura anges ska strikt förekomstkontroll tillämpas.

4.4.5.3 Särskilt undantag – Enhetsomräkning mellan MT och KG
Systemet får konvertera mellan viktenheterna:

• MT (metric ton), inklusive förkortningarna “T” och “TO” när de entydigt avser metric ton (1000 kg),
• KG (kilogram).
Fast omräkningsfaktor ska användas:
1 MT = 1000 KG

Ingen annan enhetsomräkning är tillåten.
Omräkning får endast ske när:
både numeriskt värde och enhet uttryckligen framgår i certifikatet och i fakturan, och
viktkategori är verifierbar enligt punkt 2.
Tolerans (±0,1 % eller ±0,001 av angiven enhet) ska tillämpas efter genomförd omräkning.
Om avrundning eller decimalformat medför osäkerhet ska resultatet vara MISMATCH.

4.4.5.4 Särskilt undantag – Härledning av styckvikt (strikt tillämpning)
Systemet får härleda styckvikt genom division av total vikt med antal endast när samtliga nedanstående villkor är uppfyllda:
Certifikatet anger vikt per styck eller vikt för en enskild artikel.
Fakturan innehåller exakt en artikelrad som motsvarar certifikatets varubeskrivning.
Fakturan anger uttryckligen:
– Quantity (antal), och
– Total Net Weight eller Total Gross Weight för samma artikelrad.
Ingen annan artikelrad på fakturan delar eller påverkar den angivna totalvikten.
Viktkategori (GW eller NW) är entydigt angiven och överensstämmer mellan certifikat och faktura.
Styckvikt kan beräknas genom:
total vikt ÷ antal.
Resultatet överensstämmer med certifikatets angivna vikt inom tolerans (±0,1 % eller ±0,001 av angiven enhet).
Om något av ovanstående villkor inte är uppfyllt → MISMATCH.

4.4.5.5 Särskilt undantag – Summering av flera rader inom samma faktura
Systemet får summera kvantiteter från flera rader inom samma faktura endast när samtliga nedanstående villkor är uppfyllda:
Certifikatet anger en total kvantitet för en vara.
Fakturan innehåller flera rader vars kvantiteter tillsammans motsvarar den totala kvantitet som anges i certifikatet.
Samtliga relevanta rader ska tillhöra samma faktura och samma fakturareferens som anges i certifikatet.
Samma enhet används på samtliga relevanta rader.
Ingen annan artikelrad får inkluderas i summeringen.
Vid summering får systemet endast inkludera fakturarader som avser samma vara eller modell som anges i certifikatets varubeskrivning.
Rader som avser tillval, komponenter, konfigurationsposter, kits eller andra underordnade poster får inte inkluderas i summeringen om de inte uttryckligen utgör den vara som anges i certifikatet
Summeringen sker utan omräkning eller konvertering.
Den summerade totalsumman överensstämmer med certifikatets kvantitet inom tolerans (±0,1 % eller ±0,001 av angiven enhet).
Om något av ovanstående villkor inte är uppfyllt → MISMATCH.

4.4.5.6 Särskilt undantag – Summering av radvikter när totalrad saknas
Systemet får summera vikter angivna per artikelrad i en eller flera fakturor när total vikt inte anges uttryckligen i fakturan eller fakturorna
Detta undantag får endast tillämpas när samtliga nedanstående villkor är uppfyllda.

4.4.5.6.1 Fakturareferens och avgränsning
Certifikatet ska innehålla:
– uttrycklig hänvisning till faktura, exempelvis “according to attached invoice(s)” eller motsvarande,
– fakturareferens eller referensintervall som entydigt identifierar vilka fakturor som omfattas, och
– fakturadatum.
Endast artikelrader från de fakturor som omfattas av certifikatets fakturareferenser får inkluderas i summeringen.

4.4.5.6.2 Viktangivelse per artikelrad
Varje artikelrad som inkluderas i summeringen ska innehålla en uttrycklig viktangivelse med:
– numeriskt värde, och
– viktenhet.
Om någon relevant artikelrad saknar viktangivelse eller enhet ska resultatet vara MISMATCH.

4.4.5.6.3 Enhet
Samtliga vikter som inkluderas i summeringen ska använda samma enhet.
Om olika enheter förekommer får omräkning endast ske mellan:
– KG
– MT
enligt reglerna i avsnitt 3B.

4.4.5.6.4 Avgränsning av relevanta rader
Systemet får endast inkludera artikelrader från de fakturor som omfattas av certifikatets fakturareferenser.
Följande rader får inte inkluderas i summeringen:
– fraktkostnader
– packningskostnader
– pall- eller emballagerader
– andra kostnadsrader utan varubeskrivning.
Om det inte entydigt går att avgöra vilka rader som ska inkluderas ska resultatet vara MISMATCH.

4.4.5.6.5 Viktkategori
Certifikatet ska uttryckligen ange viktkategori:
– Gross Weight (GW), eller
– Net Weight (NW).
Om fakturan inte uttryckligen anger viktkategori får artikelradernas vikt användas för verifiering endast när:
– ingen annan viktkategori förekommer i fakturan, och
– ingen uppgift i fakturan motsäger att vikten avser samma viktkategori som anges i certifikatet.
Om osäkerhet uppstår ska resultatet vara MISMATCH.

4.4.5.6.6 Verifiering
Systemet får summera de relevanta artikelradernas vikter.
Den summerade vikten ska överensstämma med certifikatets vikt inom tolerans:
±0,1 % eller ±0,001 av angiven enhet.
Om avvikelsen överstiger toleransgränsen ska resultatet vara MISMATCH.

4.4.6 MATCH / MISMATCH
MATCH föreligger när den numeriska uppgiften kan identifieras i fakturan enligt ovan.
MISMATCH föreligger när:
• värdet inte kan identifieras,
• enhet anges i både certifikat och faktura och dessa motsäger varandra
• avvikelsen överstiger toleransgränsen, eller
• KG anges utan att GW/NW specificeras i certifikatet, och inte omfattas av undantag för kombinerad viktkategori,
• GW/NW anges utan att viktenhet uttryckligen framgår i certifikatet.


4.5 Kontrollpunkt: Ursprungsland (Country of Origin)
Syfte
Systemet ska verifiera att det ursprungsland som anges i certifikatet uttryckligen framgår i den bifogade fakturan.
Verifieringen är ensidig:
Uppgiften i certifikatet ska kunna återfinnas i fakturan.
Systemet får inte göra tolkning eller anta ursprung baserat på företagsadress, exportland eller annan indirekt information.

4.5.1 Identifiering i fakturan
Systemet ska identifiera uppgift om ursprungsland i fakturan.
Relevanta benämningar kan exempelvis vara:
Country of Origin
Origin
Made in
Goods are of … origin
eller motsvarande uttryck.
Ursprungslandet ska uttryckligen framgå i text.

4.5.2 Enhetligt ursprungsland
Om fakturan endast anger ett gemensamt ursprungsland för samtliga varor är detta tillräckligt för verifiering av samtliga varor i certifikatet.
Det krävs inte att ursprungsland anges bakom varje enskild artikel om fakturan tydligt anger ett gemensamt ursprung.

4.5.3 Blandade ursprung
Om fakturan innehåller flera olika ursprungsländer ska det entydigt framgå vilket ursprungsland som avser respektive vara.
Denna koppling ska kunna fastställas:
antingen direkt i certifikatet, eller
i fakturan, om certifikatet tydligt hänvisar till fakturan.
Om fakturan inte anger ursprungsland per artikel och flera ursprung förekommer utan tydlig fördelning ska resultatet vara MISMATCH.
Systemet får inte göra tolkning eller antaganden om vilket ursprung som hör till vilken vara.

4.5.4 Normalisering
Inför jämförelse får systemet normalisera:
versaler/gemener
mindre stavningsvariationer
fullständigt landsnamn vs vedertagen kortform
Exempel:
United States / USA
Sweden / Kingdom of Sweden
Dock får ingen semantisk tolkning göras.

4.5.4.1 Särskild normalisering – Europeiska unionen
Om certifikatet anger:
European Union
European Community
EU
ska detta anses verifierat när fakturan innehåller minst ett ursprungsland som är medlemsstat i Europeiska unionen vid utfärdandedatum.
Om fakturan även innehåller ursprungsländer som inte är medlemsstater i Europeiska unionen får dessa förekomma tillsammans med EU under förutsättning att:
– dessa ursprungsländer också anges uttryckligen i certifikatet, och
– respektive ursprungsland entydigt framgår i fakturan för den eller de artiklar som berörs.
Verifieringen ska då ske enligt följande:
– varje ursprungsland som anges i certifikatet ska uttryckligen kunna identifieras i fakturan efter normalisering enligt punkt 4.5.4, och
– när fakturan innehåller flera olika ursprungsländer ska detta framgå per artikelrad eller på annat entydigt sätt i fakturan.
EU ska i detta sammanhang betraktas som en samlingsbeteckning för Europeiska unionens medlemsstater.
När EU anges i certifikatet ska varje EU-medlemsstat som förekommer som ursprung i fakturan anses omfattas av denna beteckning.
Verifieringsprincip
Verifieringen ska utgå från de ursprungsuppgifter som anges i certifikatet.
Systemet ska kontrollera att varje ursprungsland som anges i certifikatet kan identifieras i fakturan efter normalisering enligt punkt 4.
Systemet ska inte göra en fullständig analys av samtliga ursprungsländer i fakturan.
Förekomst av ytterligare ursprungsländer i fakturan som inte anges i certifikatet ska därför inte i sig medföra MISMATCH.
När fakturan innehåller flera olika ursprungsländer ska systemet endast verifiera att de ursprungsländer som anges i certifikatet kan identifieras i fakturan.

4.5.4.2 Förtydligande – EU-medlemsland
Om certifikatet anger ett specifikt EU-medlemsland som ursprungsland och fakturan anger European Union, ska ursprungsuppgiften anses verifierad.
Om certifikatet anger European Union, European Community eller EU och fakturan anger ett specifikt EU-medlemsland ska ursprungsuppgiften också anses verifierad.
Denna verifiering gäller endast när uppgifterna avser medlemsstater i Europeiska unionen vid certifikatets utfärdandedatum.

