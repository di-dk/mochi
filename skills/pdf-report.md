name: pdf-report
description: Research a topic and deliver a clean, sourced PDF report (optionally with images)

1. set_plan with: research, outline, images (if wanted), write PDF, verify.
2. web_search 1-3 focused queries; fetch_url the 2-4 best sources (prefer official/primary sources). Note URLs.
3. Outline: title, short intro, 3-6 sections with ## headings, a Sources section listing every URL used.
4. Images: comfy_txt2img (or use files the user gave), save in the workspace, reference with ![](comfy/file.png).
5. create_pdf with the Markdown. Use tables (| a | b |) for comparisons. Keep paragraphs short.
6. VERIFY: inspect_pdf (render_page=1 when you can see images) — check page count, text, images present, no
   "[missing image" placeholders. Fix and regenerate if anything is off.
7. Final answer: one-line summary + the file path.
