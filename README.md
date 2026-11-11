<p align="center"><img src="assets/mochi_small.png" width="240" alt="Mochi, an anime girl with a pink bob in a pink dress and frilly apron, holding cake and tea"></p>

# 🍡 Mochi — a cute, careful local AI agent for Windows

Mochi is an autonomous assistant that runs **entirely on your PC**: a local LLM in
[LM Studio](https://lmstudio.ai) plus ~70 sandboxed tools: files, shell, web research, a headless browser,
Windows app control (UI Automation), **vision** (she can see screenshots, pages, images and PDFs with a vision
model), documents (PDF/Word/Excel), ComfyUI images, ffmpeg media, scheduled tasks — and she **learns**:
she saves reusable skills and lessons from her own work.
Nothing goes to the cloud except the web pages she searches and fetches for you.

She's cheerful in chat, professional in her work, and **asks before doing anything risky**.

## Requirements

- Windows 10/11, Python 3.11+ (`winget install Python.Python.3.12`)
- [LM Studio](https://lmstudio.ai) with a tool-calling model. Default: **qwen3.6-35b-a3b** (~21 GB, runs well on a 16 GB GPU).
  For vision use **gemma-4-26b-a4b** (fastest in our tests, and it can see). Smaller GPU? Pick a smaller model.
- Optional: [ComfyUI](https://www.comfy.org) running on `127.0.0.1:8188` for image generation.

## Install

```powershell
git clone https://github.com/di-dk/mochi
cd mochi
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

This creates a virtual environment, installs packages and Playwright's Chromium, runs the offline
tests, adds a **Mochi** shortcut to your desktop and (if you say yes) adds the `mochi` command to your
user PATH, so you can start her from any terminal by typing `mochi`.

Already installed? Add or remove just the command:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -PathOnly     # add `mochi` to PATH
powershell -ExecutionPolicy Bypass -File .\setup.ps1 -RemovePath   # undo (old PATH is backed up)
```

## Use

Double-click **Mochi** on the desktop, or in any terminal:

```powershell
mochi                                            # chat
mochi "make a PDF about the history of Brussels" # one-shot task
```

(Without the PATH step, use `.\mochi.cmd` from the Mochi folder.)

The launcher starts LM Studio's server and loads the model if needed (first load ≈ 1 min).

Try:
- "Search the web for the best budget mechanical keyboards and save a comparison as keyboards.pdf"
- "Generate 3 images of a cozy cabin in snow and put them in cabins.pdf"
- "Every Monday at 9:00, search for AI news and save a summary"
- "Remember that I prefer short answers"
- "Open Calculator and work out 12 + 30 with its buttons" (app control, no mouse)
- "Open example.com in your browser, take a screenshot and tell me what you see" (vision model)
- "Turn sales.xlsx into a Word report with a summary table"

Everything she creates goes into `workspace\`. Ctrl+C interrupts.

**Talk to her while she works.** You don't have to wait for her to finish: type a message and press Enter
at any time ("also compare prices", "skip the images", "answer in Dutch"). She reads it before her next step
and adjusts without starting over. Type `/stop` to make her stop; it also cuts off an answer she is still writing.

| Chat command | |
|---|---|
| `/models` | list LM Studio models (size, tool + vision support) |
| `/model <n or name>` | switch model now (frees VRAM, remembers the choice) |
| `/reset` · `/tools` · `/allowed` · `/exit` | new conversation · list tools · session approvals · quit |

`mochi --model <name> "task"` uses a model for one run only.
`mochi --bench` times every tool-capable model you have (cold start, a tool-choice step, a summary) so you can
pick the fastest one that still chooses the right tool; `mochi --bench gemma qwen` limits it to matching names.

## How she works and learns

- **Plans** tasks with 3+ steps (`set_plan` / `update_plan`) and is nudged to finish unfinished steps.
- **Verifies once** before saying done: reads files back, `inspect_pdf` (and looks at a rendered page with
  vision), `view_image`, `app_read`.
- **Skills:** after a new multi-step task works she saves a recipe (`save_skill` → `workspace\skills\`). Built-in
  starter skills live in `skills\`. Their names are loaded into every session; she reads one with `read_skill`.
- **37 built-in skills:** besides her own recipes (PDF reports, videos, ComfyUI images, web and app automation),
  v0.3.0 adds 31 short recipes adapted from [Hermes Agent](https://github.com/NousResearch/hermes-agent) skills
  and rewritten for her tools and a small local model:
  research and web (`arxiv-papers`, `grounded-citations`, `competitor-news-monitor`, `rss-feeds`,
  `reddit-reading`, `blocked-page-recovery`, `youtube-content`, `price-monitor`, `maps`, `stocks`),
  writing and planning (`document-action-items`, `meeting-action-items`, `weekly-review`, `decision-brief`,
  `decision-questionnaire`, `flashcards`, `humanize-text`, `simple-english`, `creative-ideation`,
  `content-calendar`, `songwriting`) and building (`systematic-debugging`, `test-driven-development`, `spike`,
  `plan-interview`, `api-debugging`, `github-cli`, `web-app-qa`, `architecture-diagram`, `html-mockups`,
  `meme-maker`). Only the first 40 skills are listed to the model, so keep the total under that.
- **Lessons:** when something fails and she finds the fix, she saves a one-liner (`workspace\lessons.md`) that
  she follows from then on.
- **Loop breakers:** repeating the same failing call, or the same action 3 times, triggers a "change approach" hint;
  a 4th identical call in the same task is blocked instead of run again.

All of this is plain text you can read, edit or delete. She can't modify her own code, safety rules or persona.

## Safety

| | |
|---|---|
| Free | Reading/writing inside `workspace\`, web search/fetch, PDFs, ComfyUI, read-only shell commands |
| Asks first (`y` / `n` / `a` = always this session) | Deleting, files outside the workspace, other shell commands, Python, mouse/keyboard/app control, browser clicks/typing, launching apps, scheduling, clipboard reading, killing processes, POST/PUT/DELETE web requests |
| Trusted mode (optional) | `approvals.auto_allow: [launch, desktop]` in `config.local.yaml` lets her open and operate apps on her own (`video` lets `make_video` render without asking). Terminals, the Run box, Registry Editor, Task Manager, installers, shells and Win+R-style hotkeys **still ask**. `delete`, `write_outside`, `read_outside`, `overwrite`, `shell`, `python` can never be auto-allowed |
| Never | `.env`, keys, `.ssh`, credential files; destructive commands (diskpart, format, bcdedit, …); zip entries escaping their folder |
| Scheduled runs | Nobody is there to approve, so anything that needs approval is refused (trusted categories still work) |

Every prompt, tool call and approval decision is logged to `logs\audit.jsonl`.

## Tools

| Area | Tools |
|---|---|
| Files | list_dir, read_file, write_file, edit_file, copy_path, delete_path |
| Shell | run_powershell, run_python |
| Web | web_search, fetch_url, download_file |
| Files+ | find_files, search_files (grep), zip_files, unzip |
| Vision | screenshot, browser_screenshot, view_image, inspect_pdf(render_page) — the model sees the image |
| Apps (UI Automation) | list_apps, launch_app (by Start-menu name), app_inspect, app_read, app_click, app_set_text, app_keys, app_close |
| Desktop | list_windows, focus_window, mouse_click (incl. screenshot coordinates), type_text, hotkey, wait |
| Browser | browser_open / read / click / fill / screenshot / close — headless Chromium with a persistent profile |
| Documents | create_pdf, inspect_pdf, create_docx, read_document, create_spreadsheet, read_spreadsheet |
| Media | image_edit (resize/crop/rotate/convert), media_convert + media_info (ffmpeg) |
| System | system_info, list_processes, kill_process, clipboard_get / clipboard_set, notify, open_with_default_app |
| Web APIs | http_request (GET free; POST/PUT/PATCH/DELETE ask) |
| Planning & learning | set_plan, update_plan, find_skills, read_skill, save_skill, save_lesson |
| ComfyUI | comfy_status, comfy_list_models, comfy_txt2img, comfy_run_workflow (API-format JSON) |
| Schedule | schedule_task, list_scheduled_tasks, delete_scheduled_task (Windows Task Scheduler) |
| Memory | remember, recall |
| Video (optional) | make_video, list_my_videos — see [Videos](#videos-optional) |

## Videos (optional)

Mochi can make finished, voiced vertical shorts (2D cards, 3D cinematic, or quizzes) in **one tool call**:
she writes a tiny script (title, style, scenes with a spoken line + short on-screen text, or quiz questions) and
`make_video` hands it to a *studio* command that does the voice, rendering, mixing and filing. Recipe:
`skills\make-video.md`. A small local model is good at writing the script and bad at driving a long render
pipeline, so the pipeline stays outside her.

The tools only appear when you configure a studio in `config.local.yaml`:

```yaml
video:
  command: ["C:/path/to/python.exe", "C:/path/to/studio.py"]
approvals:
  auto_allow: [video]        # optional: render without asking each time
```

Studio contract (any program works):
- `<command> --check script.json`: validate only. `<command> script.json`: make the video.
  `<command> --list N`: print the last N videos.
- The script JSON has `title`, `style` (`2d` | `3d` | `quiz`), `scenes` (`[{say, text, emoji, label}]` or plain
  strings), `questions` (`[{q, options, answer, why}]`), `end`, `look`, `caption`, `hashtags`.
- The last stdout line is `RESULT {"ok": true, "video": ..., "folder": ..., "seconds": ..., "style": ...}`, or
  `RESULT {"ok": false, "error": "..."}`. The error is shown to Mochi so she can fix the script.

## Customize

- **Personality:** edit `persona.md`.
- **Settings:** copy `config.local.example.yaml` to `config.local.yaml` (git-ignored) and override
  model, context length, workspace, allowed folders, ComfyUI URL/checkpoint.
- `reasoning_effort: none` is fastest; `low`/`medium` make her think more before acting.

## Performance tips

- **Only the tools a task needs are sent to the model** (`tools.groups: auto`). About 20 core tools are always
  there; the rest sit in six groups (code, browser, desktop, docs, media, system) that load from the words in
  your request, from the skill being used, or when she calls `use_tools`. On an RTX 4080 with a 27B model this
  cut the first reply from about 30 s to about 10 s. `/tools` shows what is loaded.
- **Skills are picked for her.** When a request clearly matches one skill, its recipe is handed over with the
  request, so she doesn't spend a step looking it up (`skills.auto_match`).
- **Memory is trimmed rarely and in one go**, so LM Studio can keep reusing its cache between steps. When it is
  full, old tool results are summarised for the task at hand instead of cut off (`context.condense`).
- **A final check**: after a task that used tools she compares her answer with your request once before
  replying (`agent.final_check`). It costs one short extra model call.
- `llm.fast_model` (optional): a small second local model for condensing long pages as they arrive. It needs
  spare VRAM next to the main model, so it is off by default.

- The launcher loads the model with `--parallel 1`. LM Studio's default of 4 parallel slots (or `--gpu max`)
  can push a 35B model off the GPU and make it ~50× slower.
- Before loading the model and after each image job, Mochi asks ComfyUI to free VRAM.

## Limitations

- Vision needs a vision model (e.g. gemma-4). Local vision reads pages and images well but not perfectly
  (in tests it once mistook a paragraph for the heading). Text tools (browser_read, app_read) are more exact.
- A local model is far less capable than frontier cloud models: expect it to need clear instructions on
  long or unusual tasks.
- Most Windows apps can't run truly invisibly; UI Automation controls them without the mouse and often in
  the background, but some apps (games, canvas-based apps) only respond to real mouse/keyboard input.
- Scheduled tasks run only while the user is logged on.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest              # offline: sandbox, approvals, trusted mode, tools, skills, PDF/Word/Excel, video tools
.venv\Scripts\python.exe -m pytest -m live -s   # web, browser, desktop, Calculator via UI Automation, ComfyUI, Task Scheduler
.venv\Scripts\python.exe -m pytest -m e2e -s    # real LLM: research+image+PDF, vision, headless browser, plan/verify/learn, app on her own
```

## License

MIT

31 of the built-in skills are adapted from skills in [Hermes Agent](https://github.com/NousResearch/hermes-agent)
(MIT, Copyright (c) 2025 Nous Research). See `skills\CREDITS.txt`.
