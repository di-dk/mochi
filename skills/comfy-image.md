name: comfy-image
description: Generate good images with the local ComfyUI (checkpoint choice, sizes, prompts, checking results)

1. comfy_status — if ComfyUI isn't reachable, ask the user to start ComfyUI Desktop.
2. Use the default checkpoint unless the user asks otherwise; comfy_list_models shows options. Only SD/SDXL-style
   checkpoints work with comfy_txt2img; if one errors, save_lesson and fall back to the default.
3. Sizes: 1024x1024 square, 832x1216 portrait, 1216x832 landscape (SDXL). 512 only for quick drafts.
4. Prompt: subject first, then style, lighting, background. Negative: lowres, blurry, watermark, text, bad anatomy.
5. Try 2-4 seeds when quality matters; view_image each (vision models) and keep the best.
6. Report the saved paths (workspace/comfy/...).
