name: meme-maker
description: Make a meme PNG: pick the joke shape, get a base image, add top/bottom caption text

1. Find the dynamic in the topic: denial in chaos, rejecting A for B, impossible choice, a plan that
   backfires, escalating irony, a hot take. Pick the joke shape first, the picture second.
2. Write the captions BEFORE the image. Top line = setup, bottom line = punchline.
   Max 8-12 words per line; shorter is funnier. Use UPPERCASE.
3. Get the base image:
   - the user gave a picture: use that file; or
   - comfy_txt2img: describe ONLY the scene (who, where, expression). Put NO text or words in the prompt.
4. view_image the base. Busy or bright where the text will go? Plan to use black bars instead.
5. image_edit cannot draw text, so use run_python with Pillow:
   - Image.open(path).convert("RGB"); d = ImageDraw.Draw(im)
   - font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", im.width // 10); fall back to arialbd.ttf
   - wrap each caption to about 90% of the width (measure with d.textbbox); shrink the font when a
     caption needs more than 3 lines
   - draw centred: d.text((x, y), line, font=font, fill="white", stroke_width=max(2, size // 15),
     stroke_fill="black"); top caption near the top edge, bottom caption near the bottom edge
   - bars mode: paste the image onto a taller black canvas and draw the white text in the bars
   - im.save("memes/<short-name>.png")
6. view_image the result. Check: text readable, nothing cut off, faces not covered, spelling right.
   Not good? Switch between overlay and bars, change the font size, or make a new base image.
7. open_with_default_app the PNG if the user wants to see it right away.

RULES
- Keep captions short. Long text ruins a meme.
- The caption must fit the picture: the joke should work without any explanation.
- Nothing hateful or abusive, and nothing that targets a private person.
- Do not download famous template pictures from the web; use the user's image or a generated one.

Final answer: the captions you used and the file path. Offer one alternative caption.
