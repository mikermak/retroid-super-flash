# Retroid Super Flash: cartridge-carrousel ("slot."-stijl)

Een nieuwe manier om je spellen te kiezen. In plaats van een lijst met bestandsnamen
zie je **cartridges**: in het midden één grote, links en rechts kleinere die meeschuiven.
Op de cart staat het plaatje van het spel, eronder de naam.

Geïnspireerd op [slot.](https://github.com/slot-cfw/slot) en
[slot. advance](https://github.com/FrankieT19/slot-advance) (GPL-3.0, net als SuperFW).
Alle tekeningen (carts, hout, layout) zijn zelf gemaakt; er is geen art van slot. gekopieerd.

Voorbeelden: map `preview\` (elke afbeelding ook 3x vergroot, `-3x.png`).

## Eerst veilig testen (er wordt niets geflasht)

1. Zet `superfw-chis-slot.gba` op de SD-kaart.
2. Start de cart zoals altijd en open `superfw-chis-slot.gba` in het menu.
   De nieuwe firmware draait dan alleen vanuit het geheugen.
3. Uitzetten = de oude firmware is gewoon terug.

## Flashen (als het bevalt)

1. Zet `superfw-chis-slot.fw` op de SD-kaart.
2. Ga naar het tabblad **Info** en houd **Omlaag + B + Start** ingedrukt: flashen staat aan.
3. Ga terug naar de spellen, kies systeem **All** en zoek de grijze cart
   `superfw-chis-slot` (of zet even **Browser view** op `List`). Druk A en bevestig.
4. Alleen voor de SuperChis (`Chis`-variant). Andere carts geven "Bad FW variant!".

## Knoppen in de carrousel

| Knop | Wat het doet |
|---|---|
| Links / Rechts | vorige / volgende cart (vasthouden = snel scrollen) |
| L / R | systeem kiezen: All, GBA, GB, GBC. Systemen zonder spellen worden overgeslagen. Voorbij het eind gaan L/R naar het vorige/volgende tabblad, zoals vroeger |
| A | spel starten (eerst een korte fade naar zwart). Op een map: map openen |
| B | een map terug. In de hoofdmap: opstartopties van het spel |
| Omhoog | opstartopties (saves, patches, cheats, klok) |
| Select | bestandsbeheer (verwijderen, verbergen, naar NOR schrijven) |
| Start | instellingen. B of Start brengt je terug |

## Instellingen (tabblad met de wereldbol)

- **Theme color**: Red/Dark, Red/White (de oude Retroid-thema's), **Wood** (Hout),
  **Dark** (Donker), **Light** (Licht). Het thema geldt voor het hele menu; alleen Wood
  tekent houtnerf achter de carts.
- **Browser view**: `Carousel` (standaard) of `List` (de oude lijst, werkt nog precies zoals vroeger).
- Druk op **Save to SD card** om het te bewaren.

## Waar komen de plaatjes op de carts vandaan?

1. **Eigen label** (optioneel): `/LABELS/<naam van het spel>.bmp`, bijvoorbeeld
   `/LABELS/Tetris DX.bmp` voor `Tetris DX.gbc`. Formaat: 120x80, 16-bit BMP,
   hetzelfde als de IMGS-plaatjes. Werkt voor GBA, GB en GBC.
2. **IMGS-pakket** (wat klanten al hebben): `/IMGS/...` op basis van de spelcode.
   Alleen GBA-spellen hebben zo'n code.
3. **Geen plaatje**: een nette cart met een gekleurd etiket en de spelnaam erop
   (GBA blauw, GB crème, GBC blauwgroen).

GB- en GBC-spellen hebben dus een eigen label in `/LABELS/` nodig voor een plaatje;
anders krijgen ze het etiket met de naam.

## Wat je ziet

- Bovenin: de tabbladen zoals altijd, rechts de systemen (All / GBA / GB / GBC).
- Midden: carts. GBA = donkergrijze liggende cart, GB = grijze staande cart met
  afgeschuinde hoek, GBC = paarse staande cart, mappen = gele map.
- Onder de cart: de naam van het spel.
- Voettekst: gebruikersnaam (links), huidige map, en "12/58" (positie / aantal).
- **Gebruikersnaam**: maak een tekstbestand `USERNAME.TXT` in de hoofdmap van de SD
  met je naam (max. 10 tekens). Geen bestand = geen naam.
- **Klok**: wordt niet getoond. De SuperChis heeft geen klokchip die het menu kan lezen,
  dus er is geen echte tijd.

## Mappen

Submappen staan als gele **map-carts** vooraan in de rij (in elk systeem). A = openen,
B = terug. Firmware-bestanden (.fw) en spellen voor andere systemen (NES, SMS ...) staan als grijze
cart onder **All**. Overige bestanden (.sav, .txt) zie je alleen in de lijstweergave.

## Wat nog niet af / niet getest is

- **Niet op echte hardware getest.** Gebouwd en de tekencode is op de pc getest
  (previews), maar mGBA kan de SD-kaart van de SuperChis niet nabootsen.
- Op de **SD-variant** (512 KB) past de carrousel niet; daar blijft de lijst.
  Lite en Chis hebben hem wel.
- Het geheugen (EWRAM) van de chis-build zit op ~98,7%. Daarom staat het cover-plaatje
  nu in het SDRAM van de cart. Let bij nieuwe functies op ruimte.
- Na het starten van een spel en terugkeren speelt een fade-in; bij een fout zie je de
  normale foutmelding.
- Ideeën voor later: echte cartridge-label-art (scans) in `/LABELS/`, GB/GBC-plaatjes
  op basis van de titel in de ROM-header, een klok als een cart wél een RTC heeft,
  en de Recent-tab ook als carrousel.

## Voor ontwikkelaars

- Code: `src/carousel_gfx.c/.h` (tekenen), `src/menu_carousel.h` (menu-logica),
  `src/coverart.c` (labels laden), instelling `view=` in `ui_settings`.
- Previews opnieuw maken (WSL):
  `tools/carousel/make_previews.sh preview <label1.bmp> <label2.bmp> <label3.bmp>`
- Bouwen: `make BOARD=chis COMPRESSION_RATIO=9` (zie de build-notities in het projectgeheugen).
