# Fullrun 54 — Analys mot upprättat facit

Körning: `gpt-5.4`, prompt hash `ffa7ad303b1b`, 240 par  
Facit: upprättat i Testdata (3 par ändrades under/efter körningen)  
Originaltestresultaten är **oförändrade** — denna fil är en separat analys.

---

## Sammanfattning

| | Körningens facit (vid start) | Upprättat facit (nu) |
|---|---|---|
| PASS | 207 (86.2%) | 206 (85.8%) |
| REVIEW | 11 (4.6%) | 11 (4.6%) |
| FAIL | 22 (9.2%) | 23 (9.6%) |
| Totalt | 240 | 240 |

---

## Facitändringar under körningen (3 par)

Dessa par hade ändrat facit i testdata medan körningen pågick. Körningen använde gammalt facit — denna analys använder det upprättade.

| Par | Gammalt facit | Nytt facit | Systemsvar | Status (gammalt) | Status (nytt) |
|---|---|---|---|---|---|
| P0133 | MISMATCH | MATCH | MISMATCH | PASS | FAIL |
| P054 | MISMATCH | MATCH | MISMATCH | PASS | FAIL |
| P229 | MATCH | MISMATCH | MISMATCH | FAIL | PASS |

Nettoeffekt: +2 FAIL, -1 FAIL = +1 FAIL totalt (22 → 23).

---

## Alla FAILs mot upprättat facit (23 par)

### Nya FAILs pga facitändring (2 par)

Dessa var PASS i körningen men är FAIL mot upprättat facit. System sa MISMATCH, experten anser MATCH.

**P0133** (facit ändrat MISMATCH → MATCH, system sa MISMATCH)
- consignee: Mottagaren i certifikatet är 'MINFENG SPECIAL PAPER CO.,LTD.' men fakturan anger 'SHANDONG PUBLISHING FOREIGN TRADE COMPANY LIMITED' — certifikatets mottagarnamn saknas i fakturan
- goods_description: Certifikatet anger 'SODRA BLUE Z BLEACHED SOFTWOOD KRAFT PULP', fakturan anger 'SODRA BLUE SOFTWOOD KRAFT PULP' — kvalifikatorerna 'Z' och 'BLEACHED' saknas
- quantity: Certifikatet anger 6032 balar / 1526.850 TON gross / 1508 ADMT net, fakturan anger 4056 balar / 1026.675 TON gross / andra värden

**P054** (facit ändrat MISMATCH → MATCH, system sa MISMATCH)
- quantity: Certifikatets box 7 anger "806,617 MT" utan explicit viktkategori (GW/NW/Gross/Net) — system tillämpar formkrav 4.4.2.2

---

### Facit=MATCH, system sa MISMATCH (19 par)

System flaggar avvikelser som experten anser är OK.

#### Grupp 1 — Saknad viktkategori (GW/NW) i certifikatet (7 par)

Regel 4.4.2.2: viktkategori är formkrav. System säger MISMATCH, experten säger MATCH.

- **P002**: box 7 anger "217.508 mt" utan GW/NW — fakturan har "Total Weight Quantity: 217.508 MT"
- **P009**: box 7 anger "496.616 MT" utan GW/NW — fakturan har TOTAL NET och TOTAL GROSS
- **P0109**: box 7 anger "46740kgs" utan GW/NW — fakturan har radkvantiteter i MT
- **P0119**: box 7 anger "247.133 mt" utan GW/NW — fakturan har "Total Weight Quantity: 247.133 MT"
- **P0124**: box 7 anger "4 Kgs" utan GW/NW — fakturan har "Weight 4 kgs"
- **P0147**: box 7 anger "20000 Kg" utan GW/NW — fakturan har "20 000,00"
- **P0101**: consignee saknas i fakturan OCH saknad GW/NW — fakturan visar ej mottagarfält

#### Grupp 2 — Tvetydig punktnotation X.YYY (3 par)

Regel 4.4.3.4: X.YYY-format kan inte normaliseras (decimal vs tusentalsavskiljare).

- **P0135**: certifikat "3267 kg net" vs faktura "3.267 Kg" — 3267 kan inte verifieras mot 3.267
- **P0167**: certifikat "Gross 104.000kg" vs faktura "104.000,00 KG" — 104.000 tvetydigt
- **P242**: certifikat "17640 kg net" vs faktura "17.640 Kg" — 17640 kan inte verifieras mot 17.640

#### Grupp 3 — Övriga (9 par)

- **P0162**: consignee "Swift Egypt Limited" saknas helt i fakturan — inget mottagarfält synligt
- **P0172**: fakturan anger både "Country of origin: United Kingdom" och "EU preferential origin" — motstridiga ursprungsuppgifter (UK ej EU-medlem vid certifikatets datum)
- **P0183**: certifikatets consignee "HOP LONG TECHNOLOGY JSC ... VIETNAM" — fakturans mottagaradress saknar landangivelse (slutar vid "117000 HANOI CITY", "VIETNAM" saknas)
- **P028**: certifikat "SÖDRA BLUE - NORTHERN BLEACHED SOFTWOOD KRAFT PULP (ECF)" — fakturan saknar "(ECF)"-tillägget
- **P035**: generell varubeskrivning med fakturareferens — fakturan innehåller även varor märkta "Harmonised System" utanför COO-scope
- **P055**: certifikat refererar faktura 2510582 daterad 20250805 — fakturan saknar fakturadatum, visar bara "Shipping date 20250805"
- **P214**: certifikatet har generiska kategoritext ("Friction Spray in Sport" etc.) som saknas i fakturan
- **P0133**: se ovan (ny FAIL pga facitändring)
- **P054**: se ovan (ny FAIL pga facitändring)

---

### Facit=MISMATCH, system sa MATCH (4 par)

System godkänner par som facit anger är MISMATCH. Alla kontrollpunkter visade MATCH i systemet.

- **P0107**: facit=MISMATCH, system=MATCH — system hittade ingen avvikelse
- **P061**: facit=MISMATCH, system=MATCH — system hittade ingen avvikelse
- **P074**: facit=MISMATCH, system=MATCH — system hittade ingen avvikelse
- **P084**: facit=MISMATCH, system=MATCH — system hittade ingen avvikelse

---

## REVIEWs (11 par)

System returnerade MANUAL_REVIEW — status oavgjord tills manuell granskning sker.

| Par | Facit |
|---|---|
| P0131 | MATCH |
| P0160 | MISMATCH |
| P0164 | MATCH |
| P018 | MISMATCH |
| P0182 | MISMATCH |
| P0191 | MISMATCH |
| P078 | MISMATCH |
| P098 | MISMATCH |
| P203 | MATCH |
| P204 | MATCH |
| P216 | MISMATCH |

---

## Fullständig tabell — alla 240 par

| Par | Facit (nu) | Systemsvar | Status (mot upprättat facit) | Facit ändrat? |
|---|---|---|---|---|
| P001 | MATCH | MATCH | PASS | |
| P0011 | MISMATCH | MISMATCH | PASS | |
| P002 | MATCH | MISMATCH | FAIL | |
| P003 | MISMATCH | MISMATCH | PASS | |
| P004 | MATCH | MATCH | PASS | |
| P005 | MISMATCH | MISMATCH | PASS | |
| P006 | MATCH | MATCH | PASS | |
| P007 | MATCH | MATCH | PASS | |
| P008 | MATCH | MATCH | PASS | |
| P009 | MATCH | MISMATCH | FAIL | |
| P010 | MISMATCH | MISMATCH | PASS | |
| P0100 | MISMATCH | MISMATCH | PASS | |
| P0101 | MATCH | MISMATCH | FAIL | |
| P0102 | MISMATCH | MISMATCH | PASS | |
| P0103 | MISMATCH | MISMATCH | PASS | |
| P0104 | MISMATCH | MISMATCH | PASS | |
| P0105 | MATCH | MATCH | PASS | |
| P0106 | MATCH | MATCH | PASS | |
| P0107 | MISMATCH | MATCH | FAIL | |
| P0108 | MISMATCH | MISMATCH | PASS | |
| P0109 | MATCH | MISMATCH | FAIL | |
| P0110 | MISMATCH | MISMATCH | PASS | |
| P0111 | MATCH | MATCH | PASS | |
| P0112 | MATCH | MATCH | PASS | |
| P0113 | MISMATCH | MISMATCH | PASS | |
| P0114 | MISMATCH | MISMATCH | PASS | |
| P0115 | MATCH | MATCH | PASS | |
| P0116 | MISMATCH | MISMATCH | PASS | |
| P0117 | MISMATCH | MISMATCH | PASS | |
| P0118 | MATCH | MATCH | PASS | |
| P0119 | MATCH | MISMATCH | FAIL | |
| P012 | MATCH | MATCH | PASS | |
| P0120 | MISMATCH | MISMATCH | PASS | |
| P0121 | MISMATCH | MISMATCH | PASS | |
| P0122 | MATCH | MATCH | PASS | |
| P0123 | MATCH | MATCH | PASS | |
| P0124 | MATCH | MISMATCH | FAIL | |
| P0125 | MATCH | MATCH | PASS | |
| P0126 | MISMATCH | MISMATCH | PASS | |
| P0127 | MATCH | MATCH | PASS | |
| P0128 | MATCH | MATCH | PASS | |
| P0129 | MISMATCH | MISMATCH | PASS | |
| P013 | MISMATCH | MISMATCH | PASS | |
| P0130 | MISMATCH | MISMATCH | PASS | |
| P0131 | MATCH | REVIEW | REVIEW | |
| P0132 | MATCH | MATCH | PASS | |
| P0133 | MATCH | MISMATCH | FAIL | Ja (MISMATCH→MATCH) |
| P0134 | MISMATCH | MISMATCH | PASS | |
| P0135 | MATCH | MISMATCH | FAIL | |
| P0136 | MATCH | MATCH | PASS | |
| P0137 | MISMATCH | MISMATCH | PASS | |
| P0138 | MATCH | MATCH | PASS | |
| P0139 | MISMATCH | MISMATCH | PASS | |
| P014 | MISMATCH | MISMATCH | PASS | |
| P0140 | MATCH | MATCH | PASS | |
| P0141 | MATCH | MATCH | PASS | |
| P0142 | MATCH | MATCH | PASS | |
| P0143 | MISMATCH | MISMATCH | PASS | |
| P0144 | MISMATCH | MISMATCH | PASS | |
| P0145 | MATCH | MATCH | PASS | |
| P0146 | MATCH | MATCH | PASS | |
| P0147 | MATCH | MISMATCH | FAIL | |
| P0148 | MISMATCH | MISMATCH | PASS | |
| P0149 | MATCH | MATCH | PASS | |
| P015 | MISMATCH | MISMATCH | PASS | |
| P0150 | MATCH | MATCH | PASS | |
| P0151 | MISMATCH | MISMATCH | PASS | |
| P0152 | MISMATCH | MISMATCH | PASS | |
| P0153 | MISMATCH | MISMATCH | PASS | |
| P0154 | MATCH | MATCH | PASS | |
| P0155 | MISMATCH | MISMATCH | PASS | |
| P0156 | MATCH | MATCH | PASS | |
| P0157 | MISMATCH | MISMATCH | PASS | |
| P0158 | MISMATCH | MISMATCH | PASS | |
| P016 | MATCH | MATCH | PASS | |
| P0160 | MISMATCH | REVIEW | REVIEW | |
| P0161 | MISMATCH | MISMATCH | PASS | |
| P0162 | MATCH | MISMATCH | FAIL | |
| P0163 | MISMATCH | MISMATCH | PASS | |
| P0164 | MATCH | REVIEW | REVIEW | |
| P0165 | MATCH | MATCH | PASS | |
| P0166 | MISMATCH | MISMATCH | PASS | |
| P0167 | MATCH | MISMATCH | FAIL | |
| P0168 | MATCH | MATCH | PASS | |
| P0169 | MATCH | MATCH | PASS | |
| P017 | MATCH | MATCH | PASS | |
| P0170 | MISMATCH | MISMATCH | PASS | |
| P0171 | MATCH | MATCH | PASS | |
| P0172 | MATCH | MISMATCH | FAIL | |
| P0173 | MISMATCH | MISMATCH | PASS | |
| P0174 | MATCH | MATCH | PASS | |
| P0175 | MISMATCH | MISMATCH | PASS | |
| P0176 | MATCH | MATCH | PASS | |
| P0177 | MISMATCH | MISMATCH | PASS | |
| P0178 | MATCH | MATCH | PASS | |
| P0179 | MATCH | MATCH | PASS | |
| P018 | MISMATCH | REVIEW | REVIEW | |
| P0180 | MISMATCH | MISMATCH | PASS | |
| P0181 | MATCH | MATCH | PASS | |
| P0182 | MISMATCH | REVIEW | REVIEW | |
| P0183 | MATCH | MISMATCH | FAIL | |
| P0186 | MATCH | MATCH | PASS | |
| P0187 | MISMATCH | MISMATCH | PASS | |
| P0188 | MISMATCH | MISMATCH | PASS | |
| P0189 | MISMATCH | MISMATCH | PASS | |
| P019 | MATCH | MATCH | PASS | |
| P0190 | MISMATCH | MISMATCH | PASS | |
| P0191 | MISMATCH | REVIEW | REVIEW | |
| P0192 | MATCH | MATCH | PASS | |
| P0193 | MISMATCH | MISMATCH | PASS | |
| P0194 | MISMATCH | MISMATCH | PASS | |
| P0195 | MISMATCH | MISMATCH | PASS | |
| P020 | MISMATCH | MISMATCH | PASS | |
| P021 | MATCH | MATCH | PASS | |
| P022 | MATCH | MATCH | PASS | |
| P024 | MATCH | MATCH | PASS | |
| P025 | MISMATCH | MISMATCH | PASS | |
| P026 | MISMATCH | MISMATCH | PASS | |
| P027 | MATCH | MATCH | PASS | |
| P028 | MATCH | MISMATCH | FAIL | |
| P029 | MATCH | MATCH | PASS | |
| P030 | MATCH | MATCH | PASS | |
| P032 | MATCH | MATCH | PASS | |
| P033 | MATCH | MATCH | PASS | |
| P035 | MATCH | MISMATCH | FAIL | |
| P036 | MATCH | MATCH | PASS | |
| P038 | MISMATCH | MISMATCH | PASS | |
| P040 | MISMATCH | MISMATCH | PASS | |
| P041 | MATCH | MATCH | PASS | |
| P042 | MATCH | MATCH | PASS | |
| P043 | MISMATCH | MISMATCH | PASS | |
| P044 | MATCH | MATCH | PASS | |
| P045 | MATCH | MATCH | PASS | |
| P046 | MATCH | MATCH | PASS | |
| P047 | MISMATCH | MISMATCH | PASS | |
| P048 | MISMATCH | MISMATCH | PASS | |
| P049 | MATCH | MATCH | PASS | |
| P050 | MISMATCH | MISMATCH | PASS | |
| P051 | MATCH | MATCH | PASS | |
| P052 | MATCH | MATCH | PASS | |
| P054 | MATCH | MISMATCH | FAIL | Ja (MISMATCH→MATCH) |
| P055 | MATCH | MISMATCH | FAIL | |
| P056 | MISMATCH | MISMATCH | PASS | |
| P057 | MISMATCH | MISMATCH | PASS | |
| P058 | MISMATCH | MISMATCH | PASS | |
| P059 | MATCH | MATCH | PASS | |
| P060 | MATCH | MATCH | PASS | |
| P061 | MISMATCH | MATCH | FAIL | |
| P062 | MISMATCH | MISMATCH | PASS | |
| P063 | MISMATCH | MISMATCH | PASS | |
| P064 | MATCH | MATCH | PASS | |
| P065 | MATCH | MATCH | PASS | |
| P066 | MATCH | MATCH | PASS | |
| P067 | MATCH | MATCH | PASS | |
| P068 | MISMATCH | MISMATCH | PASS | |
| P069 | MATCH | MATCH | PASS | |
| P070 | MISMATCH | MISMATCH | PASS | |
| P071 | MISMATCH | MISMATCH | PASS | |
| P072 | MISMATCH | MISMATCH | PASS | |
| P073 | MISMATCH | MISMATCH | PASS | |
| P074 | MISMATCH | MATCH | FAIL | |
| P075 | MISMATCH | MISMATCH | PASS | |
| P076 | MISMATCH | MISMATCH | PASS | |
| P077 | MATCH | MATCH | PASS | |
| P078 | MISMATCH | REVIEW | REVIEW | |
| P079 | MATCH | MATCH | PASS | |
| P080 | MISMATCH | MISMATCH | PASS | |
| P081 | MATCH | MATCH | PASS | |
| P082 | MISMATCH | MISMATCH | PASS | |
| P083 | MATCH | MATCH | PASS | |
| P084 | MISMATCH | MATCH | FAIL | |
| P085 | MATCH | MATCH | PASS | |
| P086 | MISMATCH | MISMATCH | PASS | |
| P087 | MATCH | MATCH | PASS | |
| P088 | MATCH | MATCH | PASS | |
| P089 | MATCH | MATCH | PASS | |
| P090 | MISMATCH | MISMATCH | PASS | |
| P091 | MISMATCH | MISMATCH | PASS | |
| P092 | MATCH | MATCH | PASS | |
| P093 | MISMATCH | MISMATCH | PASS | |
| P094 | MATCH | MATCH | PASS | |
| P095 | MISMATCH | MISMATCH | PASS | |
| P096 | MISMATCH | MISMATCH | PASS | |
| P097 | MISMATCH | MISMATCH | PASS | |
| P098 | MISMATCH | REVIEW | REVIEW | |
| P099 | MATCH | MATCH | PASS | |
| P196 | MISMATCH | MISMATCH | PASS | |
| P197 | MATCH | MATCH | PASS | |
| P198 | MATCH | MATCH | PASS | |
| P199 | MATCH | MATCH | PASS | |
| P200 | MISMATCH | MISMATCH | PASS | |
| P201 | MISMATCH | MISMATCH | PASS | |
| P202 | MISMATCH | MISMATCH | PASS | |
| P203 | MATCH | REVIEW | REVIEW | |
| P204 | MATCH | REVIEW | REVIEW | |
| P205 | MISMATCH | MISMATCH | PASS | |
| P206 | MATCH | MATCH | PASS | |
| P207 | MISMATCH | MISMATCH | PASS | |
| P208 | MATCH | MATCH | PASS | |
| P209 | MISMATCH | MISMATCH | PASS | |
| P210 | MATCH | MATCH | PASS | |
| P211 | MISMATCH | MISMATCH | PASS | |
| P212 | MATCH | MATCH | PASS | |
| P213 | MISMATCH | MISMATCH | PASS | |
| P214 | MATCH | MISMATCH | FAIL | |
| P215 | MATCH | MATCH | PASS | |
| P216 | MISMATCH | REVIEW | REVIEW | |
| P217 | MATCH | MATCH | PASS | |
| P218 | MISMATCH | MISMATCH | PASS | |
| P219 | MATCH | MATCH | PASS | |
| P220 | MATCH | MATCH | PASS | |
| P221 | MATCH | MATCH | PASS | |
| P222 | MATCH | MATCH | PASS | |
| P223 | MATCH | MATCH | PASS | |
| P225 | MISMATCH | MISMATCH | PASS | |
| P226 | MATCH | MATCH | PASS | |
| P227 | MATCH | MATCH | PASS | |
| P228 | MATCH | MATCH | PASS | |
| P229 | MISMATCH | MISMATCH | PASS | Ja (MATCH→MISMATCH) |
| P230 | MISMATCH | MISMATCH | PASS | |
| P231 | MISMATCH | MISMATCH | PASS | |
| P232 | MATCH | MATCH | PASS | |
| P233 | MATCH | MATCH | PASS | |
| P234 | MATCH | MATCH | PASS | |
| P235 | MISMATCH | MISMATCH | PASS | |
| P236 | MATCH | MATCH | PASS | |
| P237 | MATCH | MATCH | PASS | |
| P238 | MATCH | MATCH | PASS | |
| P239 | MATCH | MATCH | PASS | |
| P240 | MISMATCH | MISMATCH | PASS | |
| P241 | MATCH | MATCH | PASS | |
| P242 | MATCH | MISMATCH | FAIL | |
| SEG-23D-785483 | MISMATCH | MISMATCH | PASS | |
| SEG-23D-793610 | MATCH | MATCH | PASS | |
| SEG-24D-118957 | MISMATCH | MISMATCH | PASS | |
| SEG-26D-448956 | MATCH | MATCH | PASS | |
| SEG-26D-460860 | MATCH | MATCH | PASS | |
| SEG-26D-465257 | MISMATCH | MISMATCH | PASS | |
| SEG-26D-465372 | MISMATCH | MISMATCH | PASS | |
| SEG-26D-465885 | MATCH | MATCH | PASS | |
