<!--
SPDX-FileCopyrightText: 2026 Magenta ApS <info@magenta.dk>

SPDX-License-Identifier: MPL-2.0
-->

# Suila: Datagrundlag og beregningsmotorer

Dokumentation af hvilke felter Suila modtager fra eSkat og de øvrige
dataleverancer, hvordan de enkelte felter indgår i indkomstestimaterne, samt
hvordan estimeringsmotorerne virker og udvælges.

Dokumentet er skrevet til brug for efterkontrol og gennemgang af
transaktionssporet. Det beskriver systemets faktiske adfærd, som den er
implementeret i kildekoden.

| | |
|---|---|
| Version | 1.0 |
| Dato | 21. september 2026 |
| Gælder for | Suila (beskæftigelsestilskud), produktionsversion pr. ovenstående dato |

---

## Indhold

1. [Kort om Suila](#1-kort-om-suila)
2. [Overblik over dataleverancer](#2-overblik-over-dataleverancer)
3. [Månedsredegørelsen (eSkat `monthlyincome`)](#3-månedsredegørelsen-eskat-monthlyincome)
4. [Udbytte fra AKAP (U1A) – U-indkomst](#4-udbytte-fra-akap-u1a--u-indkomst)
5. [Forskudsopgørelsen (eSkat `expectedincome`) – B-indkomst](#5-forskudsopgørelsen-eskat-expectedincome--b-indkomst)
6. [B-skattebetalinger fra Prisme](#6-b-skattebetalinger-fra-prisme)
7. [Mandtal/skatteforhold (eSkat `taxinformation`)](#7-mandtalskatteforhold-eskat-taxinformation)
8. [Årsopgørelsen (eSkat `annualincome`)](#8-årsopgørelsen-eskat-annualincome)
9. [Estimeringsmotorerne](#9-estimeringsmotorerne)
10. [Udvælgelse af estimeringsmotor](#10-udvælgelse-af-estimeringsmotor)
11. [Fra estimat til udbetaling](#11-fra-estimat-til-udbetaling)
12. [Karantæne og pause](#12-karantæne-og-pause)
13. [Årsafslutning: den faktiske årsopgørelse af Suila-tapit](#13-årsafslutning-den-faktiske-årsopgørelse-af-suila-tapit)
14. [Årshjul og forskydning](#14-årshjul-og-forskydning)
15. [Sporbarhed](#15-sporbarhed)
16. [Bilag A: Felter der modtages, men ikke indgår i beregningen](#bilag-a-felter-der-modtages-men-ikke-indgår-i-beregningen)
17. [Bilag B: Konfigurerbare parametre](#bilag-b-konfigurerbare-parametre)

---

## 1. Kort om Suila

Suila administrerer, beregner og udbetaler det særlige beskæftigelsesfradrag
*Suila-tapit*. Tilskuddet afhænger af borgerens **årsindkomst**, men udbetales
**månedligt**. Systemets kerneopgave er derfor at **estimere borgerens årsindkomst
måned for måned** og udbetale en tolvtedel af det forventede årstilskud hver måned.

Beregningen hviler på tre indkomstarter, der behandles hver for sig og til sidst
lægges sammen:

| Betegnelse | Indhold | Primær kilde |
|---|---|---|
| **A-indkomst** | Løn, indhandling, arbejdsgiverbetalt grønlandsk pension, udenlandsk pension | eSkat månedsredegørelse |
| **B-indkomst** | Selvstændig virksomhed, kapitalindkomst m.v. | eSkat forskudsopgørelse (senere: årsopgørelse) |
| **U-indkomst** | Udbytte | AKAP U1A-angivelser |

Kun A-indkomst og U-indkomst estimeres af estimeringsmotorerne. B-indkomst
hentes som et årsbeløb fra forskudsopgørelsen og lægges til uden estimering.

---

## 2. Overblik over dataleverancer

Suila modtager data fra syv leverancer. De fire første kommer fra eSkat. Alle
leverancer indgår i den månedlige kørsel.

| # | Leverance | Kilde | Teknik | Frekvens | Anvendes til |
|---|---|---|---|---|---|
| 1 | Månedsredegørelse (`monthlyincome`) | eSkat | REST-API | Månedligt | A-indkomst pr. måned |
| 2 | Forskudsopgørelse (`expectedincome`) | eSkat | REST-API | Månedligt | B-indkomst og B-udgifter for året |
| 3 | Mandtal/skatteforhold (`taxinformation`) | eSkat | REST-API | Månedligt | Skattepligtsperioder, kommunekode |
| 4 | Årsopgørelse (`annualincome`) | eSkat | REST-API | Månedligt (relevant efter årsskiftet) | Endelig årsopgørelse af Suila-tapit |
| 5 | U1A-udbytteangivelser | AKAP | REST-API | Månedligt | U-indkomst pr. måned |
| 6 | B-skattebetalinger | Prisme | SFTP (CSV) | Månedligt | Dokumentation for betalt B-skat |
| 7 | Person- og adresseoplysninger | DAFO/Pitu | REST-API | Månedligt + dagligt | Navn, adresse, civilstand, CPR-status |

Dataflowet for en månedskørsel:

```
  Månedsredegørelse ─────┐
  U1A-udbytteangivelser ─┼─►  Månedlige indkomstlinjer  ──►  Estimeringsmotorer
  B-skattebetalinger ────┘        (pr. person/måned)                 │
                                                                     ▼
  Forskudsopgørelse ───────►  B-indkomst / B-udgifter ────►  Beregningsgrundlag
                                                                     │
                                                                     ▼
  Mandtal/skatteforhold ───►  Skattepligtsperioder ───────►  Månedens Suila-tapit
                                                                     │
                                                                     ▼
                                                            Prisme (udbetaling)
```

---

## 3. Månedsredegørelsen

En månedsredegørelse er én linje pr. **borger, arbejdsgiver og måned**. En borger
kan altså have flere linjer i samme måned, hvis vedkommende har flere
arbejdsgivere; beløbene lægges sammen.

### 3.1 Felter der modtages

| Felt fra eSkat | Betydning | Indgår i A-indkomst |
|---|---|---|
| `cpr` | Borgerens CPR-nummer |  – |
| `cvr` | Arbejdsgiverens CVR-nummer | – |
| `year`, `month` | Indkomstmåned |  – |
| `salaryIncome` | Løn |  **Ja** |
| `catchsaleIncome` | Indhandling |  **Ja** |
| `employerPaidGlPensionIncome` | Arbejdsgiverbetalt grønlandsk pension |  **Ja** |
| `foreignPensionIncome` | Udenlandsk pension |  **Ja** |
| `publicAssistanceIncome` | Offentlig hjælp |  Nej |
| `alimonyIncome` | Underholdsbidrag |  Nej |
| `disGisIncome` | DIS/GIS-indkomst |  Nej |
| `retirementPensionIncome` | Alderspension |  Nej |
| `disabilityPensionIncome` | Førtidspension |  Nej |
| `ignoredBenefitsIncome` | Ikke-medregnede ydelser |  Nej |
| `civilServantPensionIncome` | Tjenestemandspension |  Nej |
| `otherPensionIncome` | Anden pension |  Nej |
| `taxMunicipalityNumber` | Skattekommunenummer | – |

> **Bemærk:** De felter, der er markeret "Nej" i sidste kolonne, gemmes i Suila og
> kan ses i transaktionssporet, men de indgår **ikke** i indkomstgrundlaget for
> Suila-tapit. De er indlæst, så grundlaget kan udvides uden ny dataleverance.

### 3.2 Beregning af A-indkomst

For hver månedsredegørelseslinje beregnes:

```
A-indkomst  =  løn
             + arbejdsgiverbetalt grønlandsk pension
             + indhandling
             + udenlandsk pension
```

Beløbet afrundes til to decimaler. Personmånedens samlede indkomst er summen af
A-indkomst og U-indkomst på tværs af alle linjer i måneden.

### 3.3 "Signal" – hvornår findes der et beregningsgrundlag

En personmåned har et **signal**, hvis mindst én af følgende er opfyldt:

- der findes mindst én indberetning i måneden med A-indkomst > 0 eller
  U-indkomst > 0, **eller**
- borgeren har betalt B-skat for måneden (se afsnit 6).

Signalet har to virkninger:

1. Der laves kun estimat for måneder med signal.
2. Der udbetales ikke Suila-tapit for en måned uden signal – beregnings­grundlaget
   sættes til 0.

---

## 4. Udbytte fra AKAP (U1A) – U-indkomst

Udbytte hentes fra AKAP's U1A-API. For hver U1A-angivelse gælder:

- Udbyttet henføres til den måned, hvor **vedtagelsesdatoen** (`dato_vedtagelse`)
  ligger.
- Beløbene fra alle poster på samme U1A lægges sammen og gemmes som **U-indkomst**
  på en indkomstlinje for den pågældende person, måned og det udloddende selskab.
- Findes borgeren ikke i forvejen i Suila, springes angivelsen over og logges.

U-indkomst estimeres på lige fod med A-indkomst, men med sin egen motor (se
afsnit 9 og 10).

---

## 5. Forskudsopgørelsen (eSkat `expectedincome`) – B-indkomst

Forskudsopgørelsen leveres pr. borger og år og kan komme i flere versioner med
hver sin `validFrom`-dato. Suila gemmer **alle** versioner, men anvender kun den
nyeste (`latest`) i beregningerne.

### 5.1 Felter der anvendes

Tre størrelser udledes af forskudsopgørelsen og lægges på borgerens år:

| Størrelse | Beregnes som |
|---|---|
| **B-indkomst** | `businessTurnover` + `catchSaleMarketIncome` + `careFeeIncome` + `capitalIncome` + `otherBIncome` |
| **B-udgifter** | `goodsComsumption` + `operatingExpensesOwnCompany` |
| **Indhandlingsudgifter** | `operatingCostsCatchSale`, dog højst `catchSaleMarketIncome` + `catchSaleFactoryIncome` og aldrig mindre end 0 |


### 5.2 Felter der modtages, men ikke anvendes

`doExpectAIncome`, `educationSupportIncome`, `alimonyIncome`, `benefitsIncome`,
`grossBusinessIncome`, `taxDepreciation`, `bussinessInterestIncome`,
`bussinessInterestExpenses`, `extraordinaryBussinessIncome`,
`extraordinaryBussinessExpenses`.

`catchSaleFactoryIncome` anvendes udelukkende som loft i beregningen af
indhandlingsudgifter, ikke som indkomst.

---

## 6. B-skattebetalinger fra Prisme

Suila henter CSV-filer med B-skatterater fra Prisme over SFTP. Hver linje
indeholder CPR, betalt beløb, opkrævet beløb, opkrævningsdato og **ratenummer**.

- Ratenummeret bruges som måned: rate 3 henføres til marts.
- Kun linjer med et **betalt beløb forskelligt fra 0** medfører, at måneden
  markeres som "B-skat betalt". Det er denne markering, der giver måneden et
  signal (afsnit 3.3).
- Det bemærkes, at Prisme kun leverer et **samlet** B-skattebeløb – det er ikke
  fordelt på de enkelte B-indkomsttyper – og at det betalte beløb kan afvige fra
  det opkrævede.

---

## 7. Mandtal/skatteforhold (eSkat `taxinformation`)

| Felt | Anvendelse |
|---|---|
| `taxScope`, `startDate`, `endDate` | Gemmes som skattepligtsperioder. Kun perioder med `taxScope = "FULL"` (fuld skattepligt) giver ret til Suila-tapit |
| `cprMunicipalityCode` | Opdaterer borgerens kommunekode |
| `catchSalePct`, `taxMunicipalityNumber`, `regionNumber`, `regionName`, `districtName` | Modtages, men gemmes ikke |

Ved hver indlæsning slettes borgerens hidtidige perioder for året og erstattes af
de netop leverede. Borgere, der ikke optræder i leverancen, får fjernet deres
perioder for året – de betragtes dermed som ikke fuldt skattepligtige.

### 7.1 Hvornår tæller en måned som skattepligtig

En måned tæller som fuldt skattepligtig, når der findes en `FULL`-periode, der

- overlapper perioden **1.–15. i måneden**, og
- dækker **månedens sidste dag**.

---

## 8. Årsopgørelsen (eSkat `annualincome`)

Årsopgørelsen leveres pr. borger og år og indeholder de endelige årsbeløb. Den
bruges **ikke** til de løbende månedlige estimater, men til den endelige opgørelse
af, hvor meget Suila-tapit borgeren rent faktisk var berettiget til (afsnit 13).

### 8.1 Felter der indgår i A-indkomsten

| Felt fra eSkat | Betydning | Bemærkning |
|---|---|---|
| `salary` | Løn | |
| `foreignPensionIncome` | Udenlandsk pension | |
| `subsidyForeignPensionIncome` | Tilskud til udenlandsk pension | |
| `otherAIncome` | Anden A-indkomst | |
| `careFeeIncome` | Plejevederlag | Kun for **indkomstår efter 2024**. For 2024 og tidligere indgår beløbet som B-indkomst |
| `occupationalBenefit` | Erhvervsmæssig ydelse | Kun for **indkomstår før 2026** |

### 8.2 Felter der indgår i B-indkomsten

| Felt fra eSkat | Betydning |
|---|---|
| `depositInterestIncome` | Renter, indlån |
| `bondInterestIncome` | Renter, obligationer |
| `otherInterestIncome` | Andre renter |
| `foreignDividendIncome` | Udenlandsk udbytte |
| `foreignIncome` | Udenlandsk indkomst |
| `groupLifeIncome` | Gruppeliv |
| `rentalIncome` | Lejeindtægt |
| `otherBIncome` | Anden B-indkomst |
| `accountShareBusinessAmount` | Andel af virksomhedsresultat |
| `careFeeIncome` | Plejevederlag – kun for **indkomstår til og med 2024** |

### 8.3 Felter der indgår særskilt

| Felt fra eSkat | Anvendelse |
|---|---|
| `pensionpayment` | Gemmes som *arbejdsgiverbetalt grønlandsk pension* og lægges til indkomstgrundlaget som en selvstændig post (ud over A, B og U) |

### 8.4 U-indkomst i årsopgørelsen

U-indkomsten indgår ikke i eSkats årsopgørelse. Den opgøres i stedet som summen
af de U-indkomster (U1A-udbytte), Suila har registreret for borgeren i året.

### 8.5 Samlet indkomstgrundlag for året

```
Indkomstgrundlag = summeret A-indkomst
                 + summeret B-indkomst
                 + summeret U-indkomst
                 + arbejdsgiverbetalt grønlandsk pension
```

### 8.6 Felter der modtages, men ikke indgår

Se [Bilag A](#bilag-a-felter-der-modtages-men-ikke-indgår-i-beregningen).

---

## 9. Estimeringsmotorerne

### 9.1 Formål og virkemåde

Estimeringsmotorernes opgave er at svare på ét spørgsmål:

> *Ud fra det, vi ved om borgerens indkomst til og med denne måned – hvad bliver
> borgerens samlede indkomst for hele året?*

Der findes fire motorer. **Alle fire beregner et estimat for alle borgere hver
måned** – også de motorer, der ikke er valgt. Det er en forudsætning for
efterfølgende at kunne måle, hvilken motor der ville have ramt bedst, og dermed
for automatisk at vælge motor til næste år (afsnit 10).

**Datagrundlag for estimering:**

- For beregningsåret *Y* indlæses borgerens månedlige indkomstlinjer for årene
  *Y-2*, *Y-1* og *Y*. Motorerne kan dermed se op til 24 måneder tilbage.
- Pr. måned bruges to tal: samlet A-indkomst og samlet U-indkomst (summeret over
  alle arbejdsgivere/selskaber).
- Estimering sker separat for A-indkomst og U-indkomst. B-indkomst estimeres
  ikke.
- Første relevante måned i året er den første måned med en indkomst forskellig
  fra 0. Måneder før denne indgår ikke.
- Der beregnes kun estimat for måneder med signal (afsnit 3.3).

### 9.2 De fire motorer

Nedenfor betegner *m* den måned, der beregnes for (1 = januar, 12 = december).

#### A. `InYearExtrapolationEngine` – Ekstrapolation af indeværende år

*Gyldig for: A-indkomst.*

Summen af årets kendte måneder til og med måned *m* ekstrapoleres til 12 måneder:

```
Årsestimat = 12 × (sum af indkomst i måned 1…m) / m
```

Indledende måneder uden indkomst afkortes først, så et årsforløb, der starter i
f.eks. maj, ikke trækkes ned af fire tomme måneder. "Huller" midt i forløbet
tæller derimod med som 0.

> *Eksempel:* Januar og maj = 0 kr., februar–april og juni–august = 10.000 kr.
> Beregning for august (*m* = 8): 12 × 60.000 / 8 = **90.000 kr.**

**Styrke:** Reagerer hurtigt på ændringer i indkomsten i indeværende år.
**Svaghed:** Følsom over for store enkeltmåneder tidligt på året.

#### B. `TwelveMonthsSummationEngine` – Sum af seneste 12 måneder

*Gyldig for: A-indkomst og U-indkomst.*

```
Årsestimat = sum af indkomst i de seneste 12 måneder (inkl. indeværende)
```

Vinduet går på tværs af årsskiftet: i marts *Y* ses på april *Y-1* til marts *Y*.

**Styrke:** Stabile indkomster og indkomster med samme mønster hvert år.
**Svaghed:** Reagerer langsomt på ændringer; enkeltstående store udbetalinger
slår igennem i 12 måneder.

#### C. `TwoYearSummationEngine` – Gennemsnit af seneste 24 måneder

*Gyldig for: A-indkomst og U-indkomst.*

```
Årsestimat = (sum af indkomst i de seneste 24 måneder) × 12/24
```

I december anvender motoren dog kun de seneste 12 måneder, dvs. den er i december
identisk med motor B.

**Styrke:** Meget svingende indkomster, hvor to års gennemsnit er et bedre bud.
**Svaghed:** Reagerer meget langsomt på reelle ændringer i indkomstniveau.

#### D. `MonthlyContinuationEngine` – Videreførelse af indeværende måned

*Gyldig for: A-indkomst og U-indkomst.*

Indeværende måneds indkomst antages at fortsætte året ud:

```
Årsestimat = (indkomst i måned m) × (12 − m + 1)
           + (sum af indkomst i måned 1…m−1)
```

> *Eksempel:* Januar–maj = 0 kr., juni = 20.000 kr. Beregning for juni (*m* = 6):
> 20.000 × 7 + 0 = **140.000 kr.**

**Styrke:** Rammer hurtigt rigtigt, når en borger starter i fast job midt på året.
**Svaghed:** Meget følsom over for engangsbeløb i den aktuelle måned.

### 9.3 Oversigt

| Motor | A-indkomst | U-indkomst | Ser tilbage | Reaktionshastighed |
|---|:---:|:---:|---|---|
| `InYearExtrapolationEngine` | ✔ | – | Indeværende år | Middel |
| `TwelveMonthsSummationEngine` | ✔ | ✔ | 12 måneder | Langsom |
| `TwoYearSummationEngine` | ✔ | ✔ | 24 måneder | Meget langsom |
| `MonthlyContinuationEngine` | ✔ | ✔ | Indeværende måned + året | Hurtig |

### 9.4 Løbende måling af træfsikkerhed

For hver borger, hvert år, hver motor og hver indkomstart beregnes der en RMSE
(root mean square error). Jo lavere RMSE er, jo bedre rammer en estimeringsmotor
årsindkomsten.
---

## 10. Udvælgelse af estimeringsmotor

### 10.1 Kriterium

Der vælges motor **pr. borger og pr. indkomstart** (A og U hver for sig) efter
ét kriterium:

> **Den motor, der havde den laveste RMSE % for borgeren i det foregående år,
> anvendes i indeværende år.**

Kun motorer med en beregnet RMSE for det foregående år indgår i sammenligningen.
Har borgeren ingen brugbar historik – f.eks. i borgerens første år i systemet, og
i systemets allerførste år – foretages der intet valg, og standardmotoren bevares.

### 10.2 Standardmotorer

| Indkomstart | Standardmotor |
|---|---|
| A-indkomst | `InYearExtrapolationEngine` |
| U-indkomst | `TwelveMonthsSummationEngine` |

### 10.3 Hvornår vælges der

Valget foretages af det årlige job `autoselect_estimation_engine`, der afvikles i
februar (efter udsendelsen af e-Boks-breve om decemberkørslen) eller i marts. Det
er en forudsætning for marts måneds indkomstestimering.

Valget kan desuden ændres manuelt pr. borger og indkomstart i
sagsbehandlergrænsefladen. En manuel ændring journaliseres automatisk som et notat
på borgerens sag med angivelse af, hvilken motor der blev ændret fra og til.

### 10.4 Sporbarhed af motorvalget

Motorvalget er versioneret. For en given udbetaling kan det derfor efterfølgende
afgøres, **hvilken motor der faktisk var gældende, da beløbet blev beregnet** –
også hvis valget senere er ændret. Systemet slår op i historikken på tidspunktet
for den seneste gennemførte beregningskørsel.

---

## 11. Fra estimat til udbetaling

Månedens beregning sker i følgende trin. Kun borgere, der er **fuldt skattepligtige
i den pågældende måned**, indgår overhovedet.

### Trin 1: Estimeret årsindkomst

For hver borger hentes estimatet fra den **valgte** motor for A-indkomst og
estimatet fra den **valgte** motor for U-indkomst, og de lægges sammen.

### Trin 2: Beregningsgrundlag

```
Beregningsgrundlag = (estimeret A+U-indkomst
                      + B-indkomst
                      − B-udgifter
                      − indhandlingsudgifter)
                     × 12 / antal fuldt skattepligtige måneder i året
```

Opskaleringen med `12 / antal skattepligtige måneder` betyder, at en borger, der
kun er skattepligtig en del af året, vurderes efter det niveau, indkomsten svarer
til på årsbasis. Tilskuddet nedskaleres igen i trin 3.

To undtagelser:

- Er der **manuelt fastsat en årsindkomst** på borgeren, anvendes den i stedet for
  hele ovenstående udtryk. Den manuelt fastsatte årsindkomst træder altså i stedet
  for både estimatet, B-indkomsten, B-udgifterne og skattepligtsskaleringen.
  Ændringen journaliseres automatisk som et notat med det indtastede beløb, og
  indeværende samt alle efterfølgende måneder genberegnes straks – dog ikke
  måneder, der allerede er sendt til Prisme.
- Har måneden **intet signal** (afsnit 3.3), sættes beregningsgrundlaget til 0.

### Trin 3: Årets forventede Suila-tapit

Beregningsgrundlaget omsættes til et årligt tilskud ved at slå op i suila-tapit
tabellen.

Derefter ganges resultatet med en **sikkerhedsfaktor** og nedskaleres til den del af
året, borgeren er skattepligtig:

```
Forventet årstilskud = årligt tilskud × sikkerhedsfaktor
                       × antal fuldt skattepligtige måneder / 12
```

Sikkerhedsfaktoren gør det muligt bevidst at udbetale lidt mindre end det fulde
beregnede beløb for at mindske risikoen for tilbagebetalingskrav. I december
sættes den altid til 1, så året gøres helt op. Sikkerhedsfaktoren er pr. i dag sat
til 1,0, dvs. der udbetales 100 % af det beregnede.

### Trin 4: Månedens beløb

```
Restbeløb for året = forventet årstilskud − allerede udbetalt i år
Månedens beløb     = restbeløb / (13 − måned)
```

Fordi hele årsestimatet genberegnes hver måned, og resten fordeles på de
resterende måneder, korrigerer systemet automatisk for tidligere for lave eller
for høje udbetalinger, efterhånden som året skrider frem.

### Trin 5: Justeringer

Herefter anvendes følgende regler i nævnte rækkefølge:

| # | Regel | Virkning |
|---|---|---|
| 1 | Negativt beløb | Sættes til 0. Suila opkræver ikke løbende |
| 2 | Bagatelgrænse | Beløb under **150 kr.** sættes til 0 |
| 3 | "Klæbende" beløb | Hvis månedens beløb afviger mindre end **5 %** fra sidste måneds beløb, udbetales præcis samme beløb som sidste måned. Gælder ikke januar og december. Formålet er at undgå små udsving fra måned til måned |
| 4 | Pause | Er borgeren sat på pause, udbetales 0 (også i december) |
| 5 | Karantæne | Se afsnit 12 |
| 6 | Afrunding | Beløbet rundes **op** til hele kroner |

Beløbet gemmes på personmåneden sammen med beregningsgrundlaget, det forventede
årstilskud, det faktiske årstilskud til dato og summen af tidligere udbetalinger i
året. Herefter overføres det til Prisme til udbetaling.

---

## 12. Karantæne og pause

### 12.1 Karantæne

Karantæne er en automatisk mekanisme, der skal begrænse risikoen for at udbetale
for meget til borgere, hvis berettigelse er usikker. En borger i karantæne får
intet udbetalt i årets første ti måneder og får i stedet beløbet udbetalt sidst på
året.

Fordelingen er konfigurerbar. Den nuværende opsætning udbetaler **11/12 af
restbeløbet i november og resten i december**.

Karantæne vurderes ud fra **det foregående år**. Der findes tre kriterier, som kan
slås til og fra hver for sig:

| Kriterium | Beskrivelse | Slået til |
|---|---|:---:|
| **Fik for meget udbetalt** | Borgeren fik sidste år udbetalt mere end **100 kr.** ud over det, decemberberegningen viste, vedkommende var berettiget til | Nej |
| **Tjener tæt på den øvre grænse** | Borgerens årsindkomst plus én standardafvigelse ville betyde, at der ikke udbetales Suila-tapit | Ja |
| **Tjener tæt på den nedre grænse** | Borgerens årsindkomst minus én standardafvigelse ville betyde, at der ikke udbetales Suila-tapit | Nej |

Når en borger sættes i eller tages ud af karantæne, oprettes automatisk et notat
på borgerens sag med begrundelsen.

### 12.2 Pause

En borger kan sættes manuelt på pause. En borger på pause får intet udbetalt –
heller ikke i december. Beløbet kommer i stedet til udbetaling, når årsopgørelsen
er færdig (august året efter).

Pausestatus er versioneret, og beregningen tager hensyn til, om borgeren var på
pause **på det tidspunkt, hvor beregningen blev foretaget** – ikke til den
nuværende status. Det registreres desuden, om det var borgeren selv eller
Skattestyrelsen, der satte pausen.

---

## 13. Årsafslutning: den faktiske årsopgørelse af Suila-tapit

Når eSkats årsopgørelse foreligger, opgøres borgerens faktiske berettigelse:

1. Indkomstgrundlaget for året opgøres som beskrevet i afsnit 8.5.
2. Der beregnes en **skattedagsandel**: antal fuldt skattepligtige dage i året
   divideret med årets antal dage (365 eller 366).
3. Indkomstgrundlaget opskaleres med skattedagsandelen, som om borgeren havde
   været skattepligtig hele året.
4. Det årlige tilskud beregnes af det opskalerede grundlag efter formlen i trin 3
   ovenfor (uden sikkerhedsfaktor).
5. Tilskuddet nedskaleres igen med skattedagsandelen.

Er skattedagsandelen 0, er tilskuddet 0.

**Resultatet** er forskellen mellem det beløb, borgeren var berettiget til, og det
beløb, der faktisk blev udbetalt i årets løb:

```
Resultat = faktisk berettiget årstilskud − faktisk udbetalt i året
```

Et positivt resultat er en efterbetaling til borgeren; et negativt resultat er et
tilbagebetalingskrav, som sendes til Prisme som en faktura. Der genereres en
årsopgørelse som PDF, som sendes til borgeren i e-Boks.

Borgere uden en gyldig adresse (tom adresse, "0", adresser der indeholder "9999",
"Ukendt" eller "Administrativ") udelades af den automatiske udsendelse.

---

## 14. Årshjul og forskydning

### 14.1 Forskydning på to måneder

Kørslerne er forskudt **to måneder**: Suila-tapit for februar udbetales i april,
for marts i maj osv. Forskydningen giver arbejdsgiverne tid til at indberette og
borgerne tid til at betale B-skat.

Konsekvens: **Løn skal være indberettet, og B-skat skal være betalt, inden
månedens beregningskørsel.** Beregningskørslen ligger 11 dage før udbetalingsdagen,
dvs. fredagen fire dage før den anden tirsdag i måneden. Fristen meldes i praksis
ud som onsdagen før den anden tirsdag for at have en margin. Er data ikke på plads,
er der ikke noget grundlag for udbetaling i den pågældende kørsel.

### 14.2 Årshjul

**Hvert år (februar, efter udsendelse af e-Boks-breve om decemberkørslen):**

1. Beregn stabilitetsscore for det foregående år.
2. Vælg bedste estimeringsmotor pr. borger og indkomstart.

**Hver måned (11 dage før udbetalingsdagen, dvs. fredagen fire dage før den anden tirsdag):**

1. Hent forskudsopgørelser, månedsredegørelser, skatteforhold og årsopgørelser fra
   eSkat.
2. Hent B-skattebetalinger fra Prisme.
3. Hent U1A-udbyttedata fra AKAP.
4. Hent person- og adresseoplysninger fra DAFO.
5. Estimér årsindkomst.
6. Beregn månedens Suila-tapit.
7. Overfør til Prisme til udbetaling.

**Hver måned (dagen før den tredje tirsdag):**

8. Udsend e-Boks-breve om udbetalingen.

**Dagligt:**

- Hent bogføringsstatus fra Prisme.
- Hent opdaterede personoplysninger fra DAFO.
- Opdatér status på afsendte e-Boks-beskeder.

Målet er, at borgeren har pengene på kontoen **den tredje tirsdag i måneden**.

### 14.3 Afhængigheder mellem jobs

Jobbene afvikles af et dagligt styringsjob, der selv holder styr på, hvilke jobs
der mangler at køre i den aktuelle periode. Et job kører kun, hvis dets
forudsætninger er opfyldt:

| Job | Forudsætter |
|---|---|
| Estimér indkomst | Indlæsning fra eSkat, Prisme B-skat, AKAP U1A og DAFO er gennemført denne måned (samt motorvalg, hvis det er marts) |
| Beregn Suila-tapit | Indkomstestimering er gennemført denne måned |
| Overfør til Prisme | Beregning er gennemført denne måned |
| Udsend e-Boks | Overførsel til Prisme er gennemført denne måned |

Er en forudsætning ikke opfyldt, springes jobbet over, og der registreres en
joblog-post med status "Afhængigheder ikke opfyldt". Jobbet kan derefter køres, når
forudsætningen er bragt i orden, uden at hele kørslen skal gentages. Et job, der
allerede er gennemført med succes i perioden, køres ikke igen.

---

## 15. Sporbarhed

Til brug for efterkontrol indeholder systemet følgende spor:

| Spor | Indhold |
|---|---|
| **DataLoad** | Én post pr. indlæsning: kilde (eskat / btax / api), tidsstempel og parametre. Hver enkelt indlæst indkomstlinje, forskudsopgørelse og årsopgørelse peger på den indlæsning, den stammer fra |
| **Historik** | Fuld versionshistorik på borger, personår, personmåned, indkomstlinjer, forskudsopgørelser og årsopgørelser: hvilken værdi blev ændret, hvornår og af hvem |
| **JobLog** | Én post pr. jobkørsel: navn, tidspunkt, parametre (år, måned, CPR, type), status (Kører / Gennemført / Fejl / Afhængigheder ikke opfyldt) og output |
| **Estimater** | Alle fire motorers estimat gemmes for hver borger, hver måned og hver indkomstart – også de motorer, der ikke blev anvendt. Sammen med estimatet gemmes det faktiske årsresultat til dato |
| **Træfsikkerhed** | ME % og RMSE % pr. borger, år, motor og indkomstart |
| **Notater** | Automatiske notater ved ændring af karantænestatus, ved manuelt skift af estimeringsmotor og ved manuelt fastsat årsindkomst – alle med begrundelse og forfatter |
| **Forskudsopgørelser** | Alle versioner gemmes med deres `validFrom`-dato; kun den nyeste er markeret som gældende |

Det er dermed muligt for en given udbetaling at rekonstruere: hvilke
indberetninger der lå til grund, hvornår de blev indlæst, hvilken motor der var
valgt på beregningstidspunktet, hvad alle fire motorer estimerede, hvilket
beregningsgrundlag der blev anvendt, og hvilke justeringsregler der blev udløst.

---

## Bilag A: Felter der modtages, men ikke indgår i beregningen

Felterne gemmes i Suila og kan ses i transaktionssporet, men påvirker ikke
beregningen af Suila-tapit.

### A.1 Månedsredegørelsen

`publicAssistanceIncome`, `alimonyIncome`, `disGisIncome`,
`retirementPensionIncome`, `disabilityPensionIncome`, `ignoredBenefitsIncome`,
`civilServantPensionIncome`, `otherPensionIncome`.

`taxMunicipalityNumber` kasseres ved indlæsning og gemmes ikke.

### A.2 Årsopgørelsen

| Felt | Betydning |
|---|---|
| `publicAssistanceIncome` | Offentlig hjælp |
| `retirementPensionIncome` | Alderspension |
| `disabilityPensionIncome` | Førtidspension |
| `ignoredBenefits` | Ikke-medregnede ydelser |
| `disGisIncome` | DIS/GIS-indkomst |
| `educationSupportIncome` | Uddannelsesstøtte |
| `alimonyIncome` | Underholdsbidrag |
| `freeJourneyIncome` | Fri rejse |
| `freeBoardIncome` | Fri kost |
| `freeLodgingIncome` | Frit logi |
| `freeHousingIncome` | Fri bolig |
| `freePhoneIncome` | Fri telefon |
| `freeCarIncome` | Fri bil |
| `freeInternetIncome` | Fri internet |
| `freeBoatIncome` | Fri båd |
| `freeOtherIncome` | Andre frie goder |
| `pensionPaymentIncome` | Pensionsudbetaling |
| `catchSaleMarketIncome` | Indhandling, marked |
| `catchSaleFactoryIncome` | Indhandling, fabrik |
| `accountTaxResult` | Skattemæssigt regnskabsresultat |
| `shareholderDividendIncome` | Aktieudbytte |

> **Opmærksomhedspunkt til efterkontrollen:** Indhandling (`catchSaleMarketIncome`
> og `catchSaleFactoryIncome`) indgår i A-indkomsten i **måneds**redegørelsen, men
> de tilsvarende felter på **års**opgørelsen indgår ikke i årsopgørelsens
> indkomstgrundlag. Aktieudbytte (`shareholderDividendIncome`) på årsopgørelsen
> indgår heller ikke; U-indkomst opgøres i stedet ud fra AKAP's U1A-angivelser.
> Dette bør bekræftes mod den forretningsmæssige forventning.

### A.3 Forskudsopgørelsen

`doExpectAIncome`, `educationSupportIncome`, `alimonyIncome`, `benefitsIncome`,
`grossBusinessIncome`, `taxDepreciation`, `bussinessInterestIncome`,
`bussinessInterestExpenses`, `extraordinaryBussinessIncome`,
`extraordinaryBussinessExpenses`.

### A.4 Mandtal/skatteforhold

`catchSalePct`, `taxMunicipalityNumber`, `regionNumber`, `regionName`,
`districtName`.

---

