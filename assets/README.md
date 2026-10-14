# Character assets

`font8x8_basic.h` is Daniel Hepper's public-domain basic Latin bitmap font,
based on Marcel Sondaar / IBM public-domain VGA fonts:
https://github.com/dhepper/font8x8/blob/master/font8x8_basic.h
Its original attribution and public-domain notice are preserved in the file.

`petscii-inspired.bin` is built by `python tools/make_charset.py`. Its text
comes from that public-domain font; its geometric symbols are drawn by the
generator under this project's MIT licence. The slots follow C64 screen codes.
It is a fallback inspired by PETSCII, not a copy of Commodore's character ROM.

No Commodore ROM is distributed. An existing VICE C64 character ROM is used
automatically if installed, or can be selected with `--charset /path/to/rom`.
