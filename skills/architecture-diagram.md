name: architecture-diagram
description: Draw a dark-themed software/cloud architecture diagram as one self-contained HTML+SVG file

Good for: system layers, cloud or network layout, microservices, database + API maps.
Not for: science drawings, physical objects, floor plans, hand-drawn looks.
1. List the components (name, type, technology) and the connections (from, to, label).
   Ask the user if any of this is unclear.
2. Plan a grid on paper first: layers top to bottom, x/y for each box. Service boxes are 60px high,
   large ones 80-120px, at least 40px gap. Put a message bus IN the gap between services.
3. write_file <project>-architecture.html: one file, inline <style> and one inline <svg>.
   No JavaScript, no external images, fonts or scripts.
4. Page: background #020617, monospace font (Consolas, monospace), light text. Parts in order: header
   (title + subtitle), the SVG inside a rounded bordered card, 3 summary cards, a small footer.
5. SVG draw order: grid pattern (40px squares, stroke #1e293b, width 0.5), then ALL arrows, then boxes
   on top so lines never cross a box face.
6. Each box: an opaque rect fill #0f172a, then the coloured rect over it (rx 6, stroke-width 1.5).
   Text sizes: name 12px, sub-label 9px, note 8px.
7. Colours by type, as fill / stroke:
   Frontend  rgba(8,51,68,0.4) / #22d3ee        Backend   rgba(6,78,59,0.4) / #34d399
   Database  rgba(76,29,149,0.4) / #a78bfa      Cloud     rgba(120,53,15,0.3) / #fbbf24
   Security  rgba(136,19,55,0.4) / #fb7185      Bus       rgba(251,146,60,0.3) / #fb923c
   External  rgba(30,41,59,0.5) / #94a3b8
8. Arrows: <line> or <path> with an arrowhead <marker>. Security flows are dashed in #fb7185.
   Boundaries: security group = dashed 4,4 rose rect; region = dashed 8,4 amber rect with rx 12.
9. Legend: OUTSIDE every boundary box, at least 20px below the lowest one. Make the viewBox tall enough.
10. Check it: browser_open("file:///" + the full path write_file reported), browser_screenshot and LOOK.
    Fix overlapping boxes, text that leaves its box, arrows that end in empty space. Then browser_close.

Final answer: one line on what the diagram shows, plus the file path.
