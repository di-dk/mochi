name: html-mockups
description: Sketch 2-3 throwaway HTML mockups of a screen so the user can compare design directions

Not for production UI or diagrams.
1. Intake, one question at a time, skipping what the user already told you:
   a) Feel: what should it feel like (adjectives, a vibe)?
   b) References: which apps or sites have that feel?
   c) Core action: what is the most important thing a user does on this screen?
2. Choose ONE axis and make 2-3 variants that sit far apart on it:
   density (compact / airy), emphasis (content-first / action-first), aesthetic (editorial /
   utilitarian / playful), layout (one column / sidebar / split), grounding (cards / bare / document).
   Variants that differ only in colour are wasted. Never build just one.
3. Name each folder after its stance: sketches/001-calm-editorial/index.html, 001-dense-utility/...
4. write_file each index.html as ONE self-contained file: inline <style>, system font stack
   ("Segoe UI", Arial, sans-serif), box-sizing reset, no external CSS, fonts, images or scripts.
5. Use realistic content: real-sounding sentences and numbers. No lorem ipsum.
6. Make it just interactive enough with a few lines of inline JS: the main button does something
   visible, one state change (filter, toggle, open/close a panel), hover styles on buttons and rows.
7. Check EVERY variant: browser_open("file:///" + its full path), browser_screenshot, LOOK. Fix collapsed layout,
   overlapping text and unstyled elements, then check again. Do not show a broken sketch.
8. Add a short README.md beside each: design stance in one sentence; key choices (layout, type,
   colour, interaction); strong at / weak at; best for.
9. Compare them in a table (density, visibility of the main action, scan-ability, feel) and give
   YOUR opinion: which is best for whom and which is weakest.
10. open_with_default_app each index.html. Ask: pick one, mix two, or another round?

RULES
- Sketches are disposable: do not reuse the code as the final product.
- Brand colours or fonts exist? Use the same few CSS variables (3 colours, 1 font) in all variants.

Final answer: the comparison table, your recommendation, the file paths, and the question in step 10.
