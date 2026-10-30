# Mina Emoji Animations — Tiny RPG Emoji Pack I

## Contents
- `animations/`: one transparent looping GIF per sprite sheet
- `previews/animation-preview.gif`: synchronized animated overview
- `previews/index.html`: browser preview grid for all individual animations
- `previews/contact-sheet.png`: static overview
- `source_sheets/`: byte-for-byte copies of the original PNG sheets
- `manifest.json`: animation metadata
- `processing-report.json`: inventory and validation report
- `SOURCE-README.html`: original pack attribution/license notice

## Animation format
- Canvas: 32 × 32 pixels
- Frame duration: 80 ms
- Loop: infinite
- Extraction: occupied cells 0–15 in row-major order from the 5 × 4 source grid
- Empty cells: 16–19 excluded
- Scaling: none; original pixel dimensions retained
- Transparency: preserved (source alpha is binary 0/255)

## Integration
Load the GIFs from `animations/`. Use `manifest.json` to enumerate names, source files, frame counts, timing, dimensions, and relative output paths.

## Source attribution
The source archive README identifies Tiny RPG – Emoji Pack I by Gabriel “tiopalada” Lima and marks it CC0 1.0.
