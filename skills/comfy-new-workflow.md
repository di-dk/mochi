name: comfy-new-workflow
description: Build and run a new ComfyUI workflow yourself when no template fits (upscale, ControlNet, new model)

1. comfy_list_models kind=all: use only models that are installed (checkpoints, unets, loras).
2. Start from the closest example: comfy_node_info template=qwen-image-edit (or wan-image-to-video) shows a working
   workflow. A workflow is JSON {"1": {"class_type": "Name", "inputs": {...}}}; a link to another node's output is
   ["<node id>", <output index>].
3. Find nodes: comfy_node_info search=upscale. Read one: comfy_node_info node=<ExactName> (inputs, allowed values,
   defaults). Never guess names or values.
4. write_file workflows/<task>.json in the workspace with your workflow, then comfy_run_workflow path=workflows/<task>.json
   (add images={"id.field": "path.png"} for inputs). ComfyUI's error names the node and the bad value: fix that one
   thing and run again. Max 4 attempts, then explain what is missing.
5. Verify the output (view_image, media_info). Only a verified workflow counts.
6. save_skill with the path of the working workflow, which inputs to set, the models it needs, and save_lesson for
   each pitfall. Next time start from the saved workflow.
VRAM is shared with the language model; comfy_run_workflow frees it afterwards. Do not run several heavy jobs at once.
