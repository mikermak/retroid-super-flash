# Retroid Super Flash: cartridge-carrousel v2 ("digitale bibliotheek")

Je spellen als **echte cartridges** in een cover-flow: in het midden de gekozen cart recht
van voren, links en rechts carts die schuin wegdraaien. Elke cart is vooraf in 3D gerenderd
(Blender) met het **echte label** van dat spel, in de juiste kleur (grijze GB, zwarte GBC,
rode Pokémon Ruby, doorzichtig blauwe Crystal, enz.). Onder de cart staan de naam, het jaar,
de uitgever en het aantal spelers.

Geïnspireerd op [slot.](https://github.com/slot-cfw/slot) en
[slot. advance](https://github.com/FrankieT19/slot-advance) (GPL-3.0); er is geen art van
slot. gebruikt.

**Credits 3D-modellen** (alle drie licentie **CC-BY-4.0**,
https://creativecommons.org/licenses/by/4.0/, van Sketchfab)
- GBA: "Gameboy Advance Cartridge" door **Vxcl** (https://sketchfab.com/vxclhd),
  https://sketchfab.com/3d-models/gameboy-advance-cartridge-38c1e6702e5d4f21af1d0930689b1d10
- Game Boy en Game Boy Color: "Gameboy cartridge" door **Val Turcea** (https://sketchfab.com/zwinkers),
  https://sketchfab.com/3d-models/gameboy-cartridge-0c4f3c521907447098df0792e6cf9a1b
- NES: "NES Cartridge" door **Anette Rana** (https://sketchfab.com/pertrosfoliea),
  https://sketchfab.com/3d-models/nes-cartridge-ce42ffeab9144a2fabf3238053d84832

Aangepast: echte labels per spel in plaats van de voorbeeldlabels, plastic per spel
ingekleurd (grijs, zwart, gekleurd, goud), schroef/printplaat van de GBA niet gerenderd.
Ook vermeld in de firmware: tabblad Info, druk A tot het paneel "Cart models (CC-BY 4.0)".
De map (folder) is een eigen model. Getest maar niet gekozen: het Game Boy-model van
Karolina D (zie `preview\v5\vergelijk-gb-modellen.png`).

De modellen staan **niet** in git. De tool zoekt ze in `firmware\library-db\models\`
(`gameboy_advance_cartridge.glb`, `gb_cart_valturcea.glb`, `nes_cart_anetterana.glb`;
ander pad: `--gba-model`, `--gb-model`, `--nes-model`). Ontbreekt er een, dan gebruikt
de tool voor dat systeem het eenvoudige eigen model.

Nieuwste voorbeelden (v5, alle modellen): map `preview\v5\`, vooral `carts-overzicht.png`
(alle carttypes naast elkaar), `donker-gb-3x.png`, `donker-gbc-3x.png`, `donker-nes-3x.png`,
`hout-alles-nes-3x.png` en `licht-nes-anim-128-3x.png`.
NES-voorbeelden v4: map `preview\v4\` (`donker-nes-3x.png`, `hout-alles-nes-3x.png`,
`licht-nes-anim-128-3x.png`).
Voorbeelden GBA/GB/GBC: map `preview\v3\` (elk plaatje ook 3x vergroot). Het mooiste:
`donker-gba-3x.png`, `hout-alles-3x.png`, `hout-gbc-3x.png`, `licht-gba-3x.png`,
`donker-anim-128-3x.png` (midden in het schuiven) en `vergelijk-gba-3x.png` (v2 naast v3).
Die previews bevatten echte labels en staan daarom niet in git.

Alleen voor de **SuperChis (chis)**. Op SD/Lite-carts blijft de gewone lijst.

## 0. Basispakket voor klanten (plug-and-play)

Kant-en-klare 3D-carts voor de officiële EU- en US-spellen van GBA, GB, GBC en NES
(één cart per spel; EU-, US- en World-versie delen er één, label bij voorkeur EU).
Spellijsten: No-Intro-DAT's (libretro-database) in `firmware\library-db\dats\`.
Na filteren (alleen officiële releases, geen beta/proto/demo/hack/homebrew/rips) en
groeperen: **GBA 1.399, GB 850, GBC 990, NES 1.490 = 4.729 spellen**.
De infokaart bevat in het basispakket alleen feiten (geen beschrijvingen).

**Volledige run (hervatbaar, zelf starten, op de achtergrond):**

```
python tools/library/maak_basispakket.py
```

Draai precies dit commando gewoon opnieuw tot hij "Klaar" zegt zonder "(deels ...)": hij
gaat steeds verder waar hij was, en stopt zelf als het Screenscraper-dagquotum bijna op is
(standaard houdt hij 300 verzoeken over; `--reserve`). Na elke run ziet je hoeveel
verzoeken er gebruikt zijn en hoeveel er over zijn.
Schatting: ~4.700 spellen, ~9.500 Screenscraper-verzoeken (quotum 10.000 per dag, dus
ongeveer 1-2 dagen), ~12-13 uur renderen, ~165 MB op de SD.
Uitvoer: `firmware\library-db\basispakket\` (map `LIBRARY` + `LEESMIJ.txt` +
`CREDITS.txt` voor de klant). Klant: map `LIBRARY` naar de SD-root kopiëren, klaar.

Testen op een steekproef (~40 spellen): `python tools/library/maak_basispakket.py --steekproef`
(uitvoer in `library-db\basispakket-test\`). Alleen tellen: `--alleen-tellen`.

**Hoe de cart een spel herkent (bestandsnaam maakt niet uit):**
1. GBA: de spelcode in de ROM (EU- en US-code wijzen naar dezelfde cart);
2. de bestandsnaam, als die gelijk is aan de No-Intro-naam;
3. GB/GBC/NES: de CRC van de ROM (NES zonder de 16-byte header). Die wordt één keer
   uitgerekend als de cart even stilstaat (een paar seconden, de cart toont zolang een
   lege cartridge) en bewaard in `LIBRARY\CRC.BIN`.

**Eigen bibliotheek + basispakket samen:** `maak_bibliotheek.py` schrijft naar dezelfde
map `LIBRARY` maar in een eigen index `MY.BIN` (carts in `LIBRARY\M\`); het basispakket
gebruikt `INDEX.BIN` (carts in `LIBRARY\C\`). Staan ze allebei op de SD, dan wint de eigen
bibliotheek. Oudere bibliotheken (v2-v6) blijven werken.

## 1. De bibliotheek maken (op de pc, één commando)

Stop de SD-kaart in de pc (bijvoorbeeld als `F:`), open een terminal in de map
`firmware\superfw-slot` en typ:

```
python tools/library/maak_bibliotheek.py --roms F:\ --uit ..\library-db\LIBRARY
```

Wat er gebeurt: alle .gba/.gb/.gbc/.nes-bestanden worden gelezen, opgezocht bij Screenscraper
(met de inlog uit de Label Builder), het label wordt gedownload en de cart wordt in Blender
gerenderd. Alles wordt bewaard in `firmware\library-db\`, dus de tweede keer gaat het
heel snel (alleen nieuwe spellen worden gedaan).

**Duur:** ongeveer 10 seconden per nieuw spel (±3 s opzoeken, ±7 s renderen).
100 spellen ≈ een kwartier. Er wordt **niets** naar de SD geschreven.

Daarna: kopieer de map **`LIBRARY`** naar de **hoofdmap** van de SD-kaart (naast je
spellen). Klaar.

Zonder ROMs testen kan ook, met een lijst spelnamen:
`python tools/library/maak_bibliotheek.py --testset tools/library/testset.txt --uit ...`
Een kant-en-klaar voorbeeld (45 bekende spellen) staat in
`firmware\library-db\voorbeeld\LIBRARY`. Die werkt op de cart als je romsbestanden
precies zo heten als in `testset.txt` (No-Intro-namen).

## 2. Eerst veilig testen (er wordt niets geflasht)

1. Zet `superfw-chis-slot.gba` op de SD-kaart.
2. Start hem vanuit je huidige menu. De nieuwe firmware draait dan alleen in het geheugen.
3. Uitzetten = de oude firmware is gewoon terug.

## 3. Flashen (als het bevalt)

1. Zet `superfw-chis-slot.fw` op de SD-kaart.
2. Tabblad **Info**: houd **Omlaag + B + Start** ingedrukt, flashen staat aan.
3. Ga naar de spellen, kies systeem **All**, zoek de grijze cart `superfw-chis-slot`
   (of zet even **Browser view** op `List`), druk A en bevestig.

## Knoppen

| Knop | Wat het doet |
|---|---|
| Links / Rechts | vorige / volgende cart (vasthouden = snel scrollen) |
| L / R | systeem: All, GBA, GB, GBC, NES (lege worden overgeslagen); voorbij het eind naar het vorige/volgende tabblad |
| A | spel starten (korte fade naar zwart); op een map: openen |
| B | map terug; in de hoofdmap: opstartopties |
| Omhoog | **infokaart** van het spel (zie hieronder) |
| Select | bestandsbeheer (verwijderen, verbergen, naar NOR) |
| Start | instellingen; B of Start brengt je terug |

**Infokaart** (Omhoog): links (of bij GBA bovenaan) het label groot, rechts naam, jaar,
uitgever, genre, spelers, regio en een korte beschrijving (Engels; Nederlands als
Screenscraper die heeft).

| Knop in de infokaart | Wat het doet |
|---|---|
| A | spel starten |
| B | terug naar de carrousel |
| Omhoog / Omlaag | tekst scrollen (beschrijving) |
| Select | opstartopties (saves, patches, cheats, klok) |

**Inzoomen (NES):** blijft een NES-cart even stilstaan, dan schuift de cart omhoog en
groter in beeld (alleen het bovenste deel, het label ~1,45x groter); de onderkant
verdwijnt achter de plank. Bij bewegen gaat hij meteen terug. GB/GBC/GBA zoomen niet in:
hun label is in de gewone stand al groot genoeg en de infokaart doet de rest.

Infokaart, inzoomen en de scherpere labels werken pas na het **opnieuw draaien van het
bibliotheek-commando** (oude LIBRARY-bestanden blijven werken: dan zonder zoom en met de
cart-render in plaats van het grote label op de kaart).

## Instellingen (tabblad met de wereldbol)

- **Theme color**: Red/Dark, Red/White, Wood (hout), Dark (donker), Light (licht).
  In de carrousel geeft elk thema een eigen achtergrond met verloop, een plank en
  schaduw onder de carts (Wood: houten plank).
- **Browser view**: `Carousel` (standaard) of `List` (de oude lijst).
- **Save to SD card** om te bewaren.

## NES-spellen

NES-spellen (.nes) hebben een eigen tabblad **NES** in de carrousel en worden getoond als
grijze NES-cartridge (model van Anette Rana) met het echte label; The Legend of Zelda en
Zelda II krijgen hun gouden cart.
Ze starten met A precies zoals in de lijst, via de emulator **PocketNES**:
- de chis-firmware heeft PocketNES al **ingebouwd**, dus het werkt zonder extra bestand;
- staat er een eigen `/.superfw/emulators/pocketnes.gba` op de SD, dan gebruikt hij die
  eerst (handig voor een nieuwere versie). Die moet je zelf downloaden.

Het bibliotheek-commando neemt .nes-bestanden vanzelf mee (de NES-cart wordt op
bestandsnaam gekoppeld: `LIBRARY/N/<romnaam>.CRT`).

## Wat je ziet als een spel niet in de bibliotheek staat

Een nette lege 3D-cart in de kleur van het systeem, met de naam op het label (uit
`LIBRARY\_BLANK\BLANK.BIN`; zonder dat bestand een eenvoudige platte kaart).
Mappen zijn gele 3D-mappen; NES-spellen een lege grijze NES-cart; firmware-bestanden en
andere systemen (SMS, PC Engine ...) lege grijze GBA-carts. Gebruikersnaam: `USERNAME.TXT` in de hoofdmap (max. 10 tekens).
Klok: niet getoond (de SuperChis heeft geen klokchip die het menu kan lezen).

## Waarom het er zo goed uit kan zien (techniek in het kort)

Het menu blijft in de 256-kleurenmodus (Mode 4, dubbel gebufferd, dus geen flikkeren of
scheuren). Maar in plaats van één gedeeld palet krijgt **elke cart-stand zijn eigen
palet-blok**: 92 kleuren voor de middelste cart, 32 voor elke schuine cart, allemaal
15-bit en vooraf op de pc met dithering berekend. Het palet wordt precies tegelijk met het
beeld gewisseld (in de V-blank), dus geen kleurflitsen. Mode 3 (15-bit) heb ik niet
gekozen: dat kan maar één beeldbuffer, waardoor animaties zouden scheuren.

## Wat nog niet af / niet getest is

- **Niet op echte hardware getest.** Alles is gebouwd en de tekencode is op de pc getest
  (previews), maar mGBA kan de SD van de SuperChis niet nabootsen. Te controleren:
  snelheid van het laden van de SD, kleuren op het scherm, de animatie.
- GB/GBC-spellen worden herkend aan hun header. Gehackte ROMs met dezelfde header
  krijgen het label van het origineel.
- Accenten (Pokémon) worden als gewone letters getoond (Pokemon), voor de zekerheid.
- Lite/SD: geen carrousel (geen ruimte in flash).
- Geheugen chis (v7): de lege carts staan niet meer in de firmware maar op de SD
  (`LIBRARY\_BLANK\BLANK.BIN`, zit in elke bibliotheek en in het basispakket) en het
  HQ-logo staat in flash in plaats van in het werkgeheugen. Werkgeheugen nu ~97,6%,
  flash ~34 KB vrij. Zonder `_BLANK` toont de carrousel een eenvoudige platte kaart.
- Japanse NES-spellen staan in een NES-cart, niet in een Famicom-cart (vervolgidee).
- Ideeën: box-art als extra stand, meer kleuren-edities, Recent-tab als carrousel.

## Voor ontwikkelaars

- Pc-tool: `tools/library/` (`maak_bibliotheek.py`, `ss.py` Screenscraper, `render_carts.py`
  Blender, `pack.py` .CRT-formaat). Lege carts: `--blanco res/carts.bin` (zit in git, eigen werk).
- Firmware: `src/carousel_gfx.{c,h}` (tekenen), `src/menu_carousel.h` (logica, laden, cache),
  "CART"-asset in `rom_boot.S`.
- Previews: `tools/carousel/make_previews.sh preview/v2 <library-db>/crt` (WSL).
