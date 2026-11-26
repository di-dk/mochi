name: comfy-edit-image
description: Edit or restyle an existing image with ComfyUI (change expression, outfit, background) keeping the rest

Use for "change her expression", "make the background night", "remove the hat", "turn this photo into anime".
1. The input must be in the workspace (uploads/... or comfy/...). comfy_status first.
2. comfy_run_workflow template=qwen-image-edit,
   images={"7.image": "uploads/photo.png"},
   set={"9.prompt": "<instruction>", "12.seed": 7, "14.filename_prefix": "edit"}. About 25-30 seconds.
3. Write the instruction in two parts: "Change <what the user asked>." then "Keep <everything else that must stay>."
   Name the things you can actually see in the picture.
   One change per run. Name things you can see. For text in images, give the exact words.
4. view_image the result and compare with the original. Wrong or too much changed: tighten "keep ..." and change the
   seed. Stop after 3 tries and tell the user what it could not do.
5. share_file the result with a caption. The original is never changed (output is a new file in comfy/).
6. Chain edits by feeding the output back as the input (images={"7.image": "comfy/<result>.png"}).
If the template fails, comfy_node_info template=qwen-image-edit shows the workflow and the inputs you can set.
