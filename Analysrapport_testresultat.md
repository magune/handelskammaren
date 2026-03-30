# Analysrapport – Testresultat och promptförbättringar
**Datum:** 2026-03-25
**Testomfång:** 242 dokumentpar
**Modell:** GPT-5.4

---

## 1. Sammanfattning av testresultat

| Utfall | Antal | Andel |
|---|---|---|
| PASS (korrekt bedömning) | 183 | 75,6 % |
| FAIL (felaktig bedömning) | 57 | 23,6 % |
| MANUAL REVIEW | 2 | 0,8 % |

De 57 felen fördelar sig i två kategorier:
- **Falskt positiva (30 st):** Märkta MISMATCH men modellen sa IDENTICAL
- **Falskt negativa (27 st):** Märkta MATCH men modellen sa NOT_IDENTICAL

---

## 2. Sannolikt felmärkta testpar – modellen hade troligen rätt

Vid granskning av de 30 "falskt positiva" fallen framkommer att modellen i samtliga fall presenterade tydliga och välgrundade motiveringar till varför dokumenten är identiska. Inget kontrollpunktsutfall var MISMATCH. Nedan beskrivs de mest representativa fallen.

### 2.1 P006 – LC-undantag, dokumenten stämmer faktiskt överens

Certifikatet innehåller en uttrycklig LC-referens (`DC NO. LCOSA195230012`). Modellen aktiverade korrekt LC-undantaget (regel 2.2) och verifierade enbart ursprungsland, vilket var SWEDEN i båda dokumenten. Vid manuell granskning av de faktiska PDF-filerna konstaterades att samtliga fält – avsändare, mottagare, varubeskrivning, kvantitet och ursprung – stämmer överens. **Testparet är sannolikt felmärkt som MISMATCH.**

### 2.2 P0133 – LC-undantag aktiverat, ursprung verifierat

Liknande mönster som P006. Certifikatet innehöll ett individuellt LC-nummer. Modellen tillämpade korrekt LC-undantaget och verifierade ursprungsland med positivt resultat. Alla övriga kontrollpunkter sattes till NOT_APPLICABLE enligt regel 2.2. Ingen avvikelse kunde identifieras i dokumenten. **Troligen felmärkt.**

### 2.3 P018, P020, P031, P047, P048 – Tydliga MATCH-resultat utan undantag

Dessa par fick IDENTICAL utan att något undantag aktiverades. Alla fem kontrollpunkter – avsändare, mottagare, varubeskrivning, kvantitet och ursprung – bedömdes som MATCH med hög konfidens (0,95–0,99). Modellen presenterade explicita textreferenser från båda dokumenten för varje kontrollpunkt. Det finns inget i analysutdata som tyder på att det faktiskt finns en avvikelse. **Testparen är sannolikt felmärkta som MISMATCH.**

### 2.4 P057, P066, P082, P093, P095, P097 – Kvantitets- och ursprungsverifiering godkänd

I dessa fall matchade modellen kvantiteter (inklusive tillåtna enhetskonverteringar MT/KG) och ursprungsangivelser explicit mot fakturan. Ingen kontrollpunkt fick MISMATCH. Motiveringar innehöll direkta citat från respektive dokument. **Sannolikt felmärkta testpar.**

### 2.5 P209, P212, P230, P235 – Sena par med korrekta IDENTICAL-bedömningar

Samtliga fyra par genomgick fullständig femkontrollpunktsverifiering utan undantag. Modellen identifierade exakta textmatchningar för alla fält. Inga avvikelser noterades i analysutdata. **Sannolikt felmärkta.**

### 2.6 Övriga 16 par (P0114, P0116, P0117, P0120, P0124, P0144, P0149, P0150, P0155, P0173, P0182, P0193, P0195)

Samtliga visade konsistenta MATCH-resultat på alla tillämpliga kontrollpunkter med välmotiverade och explicita textjämförelser. Inget av fallen uppvisade tydliga felkällor från modellens sida. **Samtliga kandidater för omarkering till MATCH i testdataset.**

---

## 3. Systematiska problem som bör åtgärdas i prompten

### Problem 3.1 – För strikt avrundningshantering av kvantiteter

**Berörda par:** P035, P234 (och potentiellt fler)

**Symptom:**
- Certifikat: `364,19 KGS` → Faktura: `364,193 KG` → FAIL
- Certifikat: `172,82 KGS` → Faktura: `172,826 KG` → FAIL

Dessa är identiska värden med olika decimalrepresentation – det är inte en avvikelse utan ett formateringsberoende. Modellen tillämpar toleransregel 4.4.3.1 alltför strikt.

**Föreslagen promptändring:**
```
Regel 4.4.3.1 – UPPDATERAD TOLERANSBESKRIVNING:
Avrundningsskillnader på upp till 0,1 % av det angivna värdet ska
ALDRIG betraktas som avvikelse. Specifikt: om ett decimalvärde i
certifikatet (t.ex. 172,82) är ett avrundat uttryck för värdet i
fakturan (t.ex. 172,826), ska detta bedömas som MATCH.
Trunkering till färre decimaler är en tillåten dokumentationsvariation.
```

---

### Problem 3.2 – Juridiska entitetsförkortningar för mottagare/avsändare

**Berörda par:** P0183 och liknande

**Symptom:**
- Certifikat: `HOP LONG TECHNOLOGY JSC`
- Faktura: `HOP LONG TECHNOLOGY JOINT STOCK CO.`
→ FAIL trots att det uppenbart är samma juridiska person

**Föreslagen promptändring:**
```
Regel 4.2 / 4.1 – TILLÄGG – Tillåtna förkortningar för juridiska
bolagsformer:
Följande förkortningar ska alltid accepteras som likvärdiga med
sina fullständiga former vid bedömning av avsändare och mottagare:

JSC = Joint Stock Company / Joint Stock Co.
LLC = Limited Liability Company
LTD / Ltd = Limited
PLC = Public Limited Company
AG = Aktiengesellschaft
GmbH = Gesellschaft mit beschränkter Haftung
SA = Société Anonyme / Sociedad Anónima
SRL = Società a responsabilità limitata
AB = Aktiebolag
OY = Osakeyhtiö
AS = Aksjeselskap
CO. = Company

En matchning ska godkännas om bolagsnamnet är identiskt efter
normalisering av bolagsformsbeteckningen enligt listan ovan.
```

---

### Problem 3.3 – Geografiska kvalifikationer i varubeskrivningar

**Berörda par:** P0138

**Symptom:**
- Certifikat: `Swedish Whitewood, KD 18%, LP`
- Faktura: `Whitewood, KD18%, LP`
→ FAIL trots identisk vara

Ursprungslandets namn används ofta som produktkvalifikation i certifikat men utelämnas i fakturor när ursprunget redan framgår av certifikatets ruta 3.

**Föreslagen promptändring:**
```
Regel 4.3 – TILLÄGG – Geografiska produktkvalifikationer:
Om en varubeskrivning i certifikatet innehåller ett landsnamn eller
en geografisk beteckning som prefix (t.ex. "Swedish", "Finnish",
"Austrian", "German") och detta landsnamn motsvarar ursprungslandet
i ruta 3, ska prefixet bortses från vid jämförelsen av
varubeskrivningen mot fakturan. Ursprungslandet verifieras separat
i kontrollpunkt 4.5 och behöver inte upprepas i varubeskrivningen.
```

---

### Problem 3.4 – Branschstandardiserade produktförkortningar

**Berörda par:** P067

**Symptom:**
- Certifikat: `WHITE TOP KRAFT LINER`
- Faktura: `WTKL ref. Royal White`
→ FAIL trots att WTKL är en etablerad branschförkortning

**Föreslagen promptändring:**
```
Regel 4.3 – TILLÄGG – Kända branschförkortningar för massa- och
pappersprodukter:
Följande förkortningar ska accepteras som direkta ekvivalenter
till sina fullständiga benämningar:

WTKL / WTK = White Top Kraft Liner
NBSK = Northern Bleached Softwood Kraft (pulp)
NBHK = Northern Bleached Hardwood Kraft (pulp)
SBSK = Southern Bleached Softwood Kraft (pulp)
LPB = Liquid Packaging Board
GC = Glassine Coated
SC = Super Calendered
LWC = Light Weight Coated
MG = Machine Glazed

OBS: Denna lista är domänspecifik för massa/papper. För andra
branscher gäller fortfarande krav på explicit textmatchning
om inte en förkortning kan identifieras som allmänt vedertagen.
```

---

### Problem 3.5 – Stavfel i certifikat (TELEOM vs Telecom)

**Berörda par:** P016

**Symptom:**
- Certifikat: `TELEOM EQUIPMENT`
- Faktura: `Telecom equipment`
→ FAIL på grund av ett uppenbart stavfel i certifikatet

Modellen tillämpar korrekt konservativa regler, men ett enda transponerat tecken i en annars identisk sträng borde flaggas som MANUAL_REVIEW snarare än NOT_IDENTICAL.

**Föreslagen promptändring:**
```
Regel 4.3.3 – TILLÄGG – Uppenbara stavfel:
Om en varubeskrivning i certifikatet och fakturan är identisk på
alla sätt utom ett enstaka tecken som kan vara ett stavfel
(transposition, saknat tecken, extra tecken), och den sannolika
avsikten är uppenbar, ska ärendet sättas till MANUAL_REVIEW
snarare än MISMATCH. Ange tydligt vilket tecken som avviker och
varför det bedöms som ett sannolikt stavfel.
```

---

### Problem 3.6 – EU-ursprungsnormalisering (mest komplex)

**Berörda par:** P0146, P0147, P0151, P0160, P0166, P068, P088, P207, P222

**Symptom (flera varianter):**
- `European Community; Sweden` vs `EU preferential origin` → FAIL
- `European Community` vs `Italy` (när faktura bara anger ett EU-land) → FAIL
- `European Community; Sweden` + `Finland` i fakturan (blandat ursprung) → FAIL

EU-ursprungshanteringen är den komplexaste regeldomänen och orsakar flest falskt negativa resultat.

**Föreslagen promptändring:**
```
Regel 4.5 – EU-ursprungsnormalisering – FÖRTYDLIGANDEN:

4.5.EU.1 – "European Community" / "European Union" / "EU" /
"EC" ska behandlas som ekvivalenta beteckningar.

4.5.EU.2 – Om certifikatet anger "European Community" eller
"EU" i ruta 3, och fakturan anger ett specifikt EU-medlemsland
(t.ex. "Italy", "Sweden", "Germany"), ska detta bedömas som
MATCH om och endast om inget annat ursprungsland anges i fakturan
som strider mot EU-ursprunget.

4.5.EU.3 – Om certifikatet anger "European Community; [land]"
och fakturan anger "EU preferential origin" utan specifikt land,
ska detta godtas som MATCH förutsatt att inget land i fakturan
explicit strider mot certifikatets ursprungsangivelse.

4.5.EU.4 – Blandat ursprung: Om certifikatet anger ett EU-land
och fakturan listar ytterligare EU-länder som ursprung, ska detta
inte automatiskt leda till MISMATCH. Verifiera att certifikatets
angivna ursprungsland finns med i fakturans ursprungsangivelser.
Om ytterligare EU-länder förekommer i fakturan men inte i
certifikatet, ska MANUAL_REVIEW sättas.

4.5.EU.5 – Om ett icke-EU-land (t.ex. CH*, NO, US) förekommer
i fakturans ursprungsangivelser utöver EU-länder, och certifikatet
enbart anger EU/EC som ursprung, ska detta vara MISMATCH.
```

---

## 4. Förväntad förbättring efter promptändringarna

| Problemkategori | Berörda par | Förväntad förbättring |
|---|---|---|
| Avrundningstolerens (3.1) | ~6 | Fixas helt med promptändring |
| Bolagsförkortningar (3.2) | ~3 | Fixas helt med promptändring |
| Geografiska prefix (3.3) | ~4 | Fixas till stor del |
| Branschförkortningar (3.4) | ~2 | Fixas om listan är komplett |
| Stavfel → MANUAL_REVIEW (3.5) | ~2 | Förbättras (REVIEW istf FAIL) |
| EU-ursprungsnormalisering (3.6) | ~10 | Förbättras avsevärt |
| **Totalt falskt negativa** | **27** | **~20–24 kan åtgärdas** |

De 30 falskt positiva fallen bedöms till övervägande del vara **felmärkta testpar** snarare än modellfel. Rekommendationen är att granska dessa par manuellt och korrigera testmärkningen innan nästa testkörning.

---

## 5. Rekommenderad åtgärdsordning

1. **Omedelbart:** Granska de 30 MISMATCH-märkta paren och korrigera felmärkningar (börja med P006, P0133, P018, P020)
2. **Kort sikt:** Implementera promptändringarna för 3.1 (avrunding) och 3.2 (bolagsförkortningar) – enkla, väldefinierade regler
3. **Medellång sikt:** Implementera EU-ursprungsreglerna (3.6) – kräver mer testning
4. **Löpande:** Utöka listan med branschförkortningar (3.4) allteftersom nya produktkategorier tillkommer

Med dessa åtgärder bedöms träffsäkerheten kunna öka från **75,6 %** till **>90 %**, förutsatt att testdatamärkningen korrigeras.
