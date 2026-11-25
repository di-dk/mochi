name: comfy-image
description: Generate good images with the local ComfyUI (checkpoint choice, sizes, prompts, checking results)

1. comfy_status. If ComfyUI is not reachable, tell the user to start it; do not try other ways to draw the image.
2. comfy_list_models kind=all. Image checkpoints are the ones NOT marked audio. If none exist, say so: Qwen/Wan models
   cannot make a picture from text here, only edit or animate one (see comfy-edit-image, comfy-animate-image).
3. comfy_txt2img with the default checkpoint unless asked otherwise. Anime/illustration models (nova3DCGXL, Illustrious
   style) like tag prompts: "1girl, pink hair, maid dress, holding cake, masterpiece, best quality, detailed".
   Realistic models like sentences. Put the subject first, then style, lighting, background.
4. Sizes (SDXL): 1024x1024 square, 832x1216 portrait, 1216x832 landscape. 25-30 steps, guidance 5-7.
   Quick drafts: 768x768, 20 steps.
5. Negative: lowres, blurry, watermark, text, bad anatomy, extra fingers.
6. view_image the result (vision models). If it is bad, change ONE thing (prompt wording, seed, guidance) and retry,
   at most 3 times. When quality matters try 2-3 seeds and keep the best.
7. Show it: share_file with a short caption (also gives the user the path). Say the prompt and seed you used.
8. If a checkpoint fails, save_lesson with its name and fall back to the default.
