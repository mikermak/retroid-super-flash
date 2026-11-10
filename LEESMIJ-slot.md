# Retroid Super Flash: cartridge-carrousel v2 ("digitale bibliotheek")

Je spellen als **echte cartridges** in een cover-flow: in het midden de gekozen cart recht
van voren, links en rechts carts die schuin wegdraaien. Elke cart is vooraf in 3D gerenderd
(Blender) met het **echte label** van dat spel, in de juiste kleur (grijze GB, zwarte GBC,
rode Pokémon Ruby, doorzichtig blauwe Crystal, enz.). Onder de cart staan de naam, het jaar,
de uitgever en het aantal spelers.

Geïnspireerd op [slot.](https://github.com/slot-cfw/slot) en
[slot. advance](https://github.com/FrankieT19/slot-advance) (GPL-3.0). De carts zijn eigen
3D-modellen op echte maten; er is geen art van slot. gebruikt.

Voorbeelden: map `preview\v2\` (elk plaatje ook 3x vergroot). Het mooiste:
`hout-gbc-3x.png`, `donker-gba-3x.png`, `licht-gba-3x.png`, `hout-gb-3x.png`,
en `donker-anim-128-3x.png` (midden in het schuiven).
Die previews bevatten echte labels en staan daarom niet in git.

Alleen voor de **SuperChis (chis)**. Op SD/Lite-carts blijft de gewone lijst.

## 1. De bibliotheek maken (op de pc, één commando)

Stop de SD-kaart in de pc (bijvoorbeeld als `F:`), open een terminal in de map
`firmware\superfw-slot` en typ:

```
python tools/library/maak_bibliotheek.py --roms F:\ --uit C:\Users\aruur\Documents\Retroid\firmware\library-db\LIBRARY
```

Wat er gebeurt: alle .gba/.gb/.gbc-bestanden worden gelezen, opgezocht bij Screenscraper
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
| L / R | systeem: All, GBA, GB, GBC (lege worden overgeslagen); voorbij het eind naar het vorige/volgende tabblad |
| A | spel starten (korte fade naar zwart); op een map: openen |
| B | map terug; in de hoofdmap: opstartopties |
| Omhoog | opstartopties (saves, patches, cheats, klok) |
| Select | bestandsbeheer (verwijderen, verbergen, naar NOR) |
| Start | instellingen; B of Start brengt je terug |

## Instellingen (tabblad met de wereldbol)

- **Theme color**: Red/Dark, Red/White, Wood (hout), Dark (donker), Light (licht).
  In de carrousel geeft elk thema een eigen achtergrond met verloop, een plank en
  schaduw onder de carts (Wood: houten plank).
- **Browser view**: `Carousel` (standaard) of `List` (de oude lijst).
- **Save to SD card** om te bewaren.

## Wat je ziet als een spel niet in de bibliotheek staat

Een nette lege 3D-cart in de kleur van het systeem, met de naam op het label.
Mappen zijn gele 3D-mappen, firmware-bestanden en andere systemen (NES, SMS ...) lege
grijze GBA-carts. Gebruikersnaam: `USERNAME.TXT` in de hoofdmap (max. 10 tekens).
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
- Ideeën: box-art als extra stand, meer kleuren-edities, Recent-tab als carrousel.

## Voor ontwikkelaars

- Pc-tool: `tools/library/` (`maak_bibliotheek.py`, `ss.py` Screenscraper, `render_carts.py`
  Blender, `pack.py` .CRT-formaat). Lege carts: `--blanco res/carts.bin` (zit in git, eigen werk).
- Firmware: `src/carousel_gfx.{c,h}` (tekenen), `src/menu_carousel.h` (logica, laden, cache),
  "CART"-asset in `rom_boot.S`.
- Previews: `tools/carousel/make_previews.sh preview/v2 <library-db>/crt` (WSL).
