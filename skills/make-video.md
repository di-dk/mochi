name: make-video
description: Make voiced short videos (2D, 3D or quiz) in ONE make_video call each; list them with list_my_videos

RULES (this is what makes you fast):
- ONE video = ONE make_video call. Do NOT list folders, read old videos, open the video pipeline or write code.
  The tool voices (the user's fixed voice), renders, mixes and files the video by itself.
- Never call list_dir / find_files / run_powershell on the Videos folders. To see what exists: list_my_videos.
- Files land in <Videos>/mochi/<style>/<date>_<slug>/  (video.mp4, script.json, caption.txt, thumb.jpg) and in
  <Videos>/mochi/INDEX.csv. That IS the organized folder; don't create or move folders yourself.
- If make_video returns ERROR, read the message, fix ONLY what it says, call once more. Never loop.
- When it says DONE, look at the attached thumbnail once, then tell the user the path. Don't render again.

STEPS:
1. Pick the style: user says 3D/cinematic -> "3d"; quiz/test/guess -> "quiz"; otherwise "2d".
   (If unsure, 2d is fastest.) For several videos, do them one after another, one call each.
2. Write the script in your head, then call make_video:
   - 4-8 scenes. Scene 1 is the HOOK: a surprising question or claim, max 10 words.
   - say: 1-2 short spoken sentences (max ~25 words). Plain words, numbers as words when spoken
     ("eight minutes"), no emoji or symbols in say.
   - text: 3-8 words on screen; put the key words in *stars*. Emoji go in "emoji" (2D only), one per scene.
   - end: a comment-bait question ("Which one surprised you?").
   - Only TRUE facts you are sure of. If unsure about a number, leave it out.
   - quiz: 2-5 questions, 3 options each, answer = the exact option text, why = one short reason.
     Give one hook scene too (e.g. "Only 1 in 10 people get all three.").
   - 3d looks: planet (space), crystal (math/gems/gold), cubes (data/money/growth), orbs (anything calm).
3. Report: title, style, length, the video path. Offer to make another.

EXAMPLE (2d):
make_video(title="Why bees build hexagons", style="2d", end="Which animal is the best engineer?", scenes=[
 {"say": "Why do bees build hexagons, and not squares?", "text": "Why *hexagons?*", "emoji": "🐝"},
 {"say": "Wax is expensive. Bees eat about eight grams of honey to make one gram of wax.", "text": "Wax costs *8 g of honey*", "emoji": "🍯"},
 {"say": "Only three shapes tile a surface with no gaps: triangles, squares and hexagons.", "text": "Only *3 shapes* fit with no gaps", "emoji": "🔺"},
 {"say": "The hexagon holds the most honey for the least wax.", "text": "Most space, *least wax*", "emoji": "🏆"}])

EXAMPLE (quiz):
make_video(title="Space quiz", style="quiz", end="How many did you get right?",
 scenes=[{"say": "Only one in ten people get all three right.", "text": "Only *1 in 10* get all 3", "emoji": "🚀"}],
 questions=[{"q": "Which planet is the hottest?", "options": ["Mercury", "Venus", "Mars"], "answer": "Venus", "why": "Its thick air traps heat."},
            {"q": "How long does sunlight take to reach Earth?", "options": ["8 seconds", "8 minutes", "8 hours"], "answer": "8 minutes", "why": "About 8 min 20 s."}])

EXAMPLE (3d): same as 2d but style="3d", look="planet" (no emoji needed; text with *stars* becomes elegant italics).
