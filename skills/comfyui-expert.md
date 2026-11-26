name: comfyui-expert
description: Expert playbook for ComfyUI: pick the right tool, write strong prompts, recover from every failure

Use for ANY picture, video, animation or image-edit request. Never guess what is installed.
1. First call comfy_capabilities (cheap). Video models are NOT checkpoints. It says which tool is READY.
2. Pick the tool (one call does the job, do not assemble workflows by hand):
   - "make a video / animation / clip": comfy_video(prompt=...). With a picture: comfy_video(prompt=<motion>, image=path).
   - "picture of X": comfy_txt2img (anime/illustration tags work best with the default checkpoint).
   - "change / edit this picture": comfy_run_workflow template=qwen-image-edit (see comfy-edit-image).
   - "draw yourself": draw_myself. Music, sound, upscaling: the capability list says what is still missing; build it
     with comfy-new-workflow, or tell the user it is not set up.
3. Video prompt = ONE vivid sentence about what the USER asked for: the subject they named + what it does + where +
   light or camera. Use their subject, never another one, and never a sentence from these instructions. Real motion
   verbs. No text or logos in the scene. Default 2 seconds, square. More seconds (max 5) or other shapes (landscape, portrait) only if asked.
   Times: about 30 to 90 seconds. One heavy job at a time; do not start a second one while one runs.
4. The GPU is shared with your own language model: it is unloaded automatically before a job and loads again by itself.
5. When something fails, read the message: it says what to do.
   - "out of GPU memory": comfy_video already retried smaller; if it still fails, say so and offer a smaller size or
     fewer seconds. Never repeat the same call more than once.
   - "ComfyUI is not running": comfy_start (it asks the user), then retry the original request once.
   - "Value not in list" or a missing model: comfy_list_models kind=all, then use an exact name.
   - "no input X" or a wrong key: use comfy_video / draw_myself, or read the template with comfy_node_info template=...
   - Not sure a template still works: comfy_check.
6. Never say a picture or video was made unless the tool returned a file path. After success the chat already shows it:
   add one friendly line with the prompt and seed, and offer a variation (new seed, longer, other style).
7. When you solve a NEW kind of failure, save_lesson with what really happened and what fixed it (never an invented one).
