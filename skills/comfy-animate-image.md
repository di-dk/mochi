name: comfy-animate-image
description: Turn a still image into a short video with ComfyUI (blink, smile, hair sway, simple motion)

Use for "animate this picture", "make her blink and smile", "make a looping avatar".
1. Input image in the workspace, ideally square or portrait, one clear subject. comfy_status first.
2. Easiest: comfy_video(prompt=<motion>, image=path) does everything below for you (size, frames, seeds, retry on
   low GPU memory). By hand: comfy_run_workflow template=wan-image-to-video,
   images={"9.image": "comfy/pic.png"},
   set={"10.text": "<motion>", "12.width": 480, "12.height": 480, "12.length": 33, "13.noise_seed": 5, "14.noise_seed": 5}.
   33 frames = 2 seconds at 16 fps and takes about 30 seconds. Longer (49-81 frames) or bigger (640+) is slower
   and may run out of VRAM: only do it if asked.
3. Describe MOTION, not the picture: who or what moves and how (use the real subject of the picture).
   Add "no camera movement, same character" to keep the face stable. Small motions work best; big ones distort.
4. The result is a .webm in comfy/. Check it: media_info, and view_image a frame via media_convert if needed.
   Wrong result: simplify the motion, change the seed, retry at most 3 times.
5. share_file the video: the chat shows a thumbnail that plays big when clicked.
6. Looping: only if asked, ping-pong it with ffmpeg (run_shell asks first):
   ffmpeg -i in.webm -filter_complex "[0]split[a][b];[b]reverse[r];[a][r]concat=n=2:v=1" out.webm
