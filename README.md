# 🍡 Mochi — a cute, careful local AI agent for Windows

Mochi is an autonomous assistant that runs **entirely on your PC**: a local LLM in
[LM Studio](https://lmstudio.ai) plus 35 sandboxed tools for files, shell, web research,
browser and desktop control, PDFs, ComfyUI image generation and scheduled tasks.
Nothing goes to the cloud except the web pages she searches and fetches for you.

She's cheerful in chat, professional in her work, and **asks before doing anything risky**.

## Requirements

- Windows 10/11, Python 3.11+ (`winget install Python.Python.3.12`)
- [LM Studio](https://lmstudio.ai) with a tool-calling model. Default: **qwen3.6-35b-a3b** (~21 GB, runs well on a 16 GB GPU).
  Smaller GPU? Pick a smaller model in `config.local.yaml`.
- Optional: [ComfyUI](https://www.comfy.org) running on `127.0.0.1:8188` for image generation.

## Install

```powershell
git clone <this repo> mochi
cd mochi
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

This creates a virtual environment, installs packages and Playwright's Chromium, runs the offline
tests and adds a **Mochi** shortcut to your desktop.

## Use

Double-click **Mochi** on the desktop, or:

```powershell
.\mochi.cmd                                  # chat
.\mochi.cmd "make a PDF about the history of Brussels"   # one-shot task
```

The launcher starts LM Studio's server and loads the model if needed (first load ≈ 1 min).

Try:
- "Search the web for the best budget mechanical keyboards and save a comparison as keyboards.pdf"
- "Generate 3 images of a cozy cabin in snow and put them in cabins.pdf"
- "Every Monday at 9:00, search for AI news and save a summary"
- "Remember that I prefer short answers"

Everything she creates goes into `workspace\`. Chat commands: `/reset`, `/tools`, `/allowed`, `/exit`. Ctrl+C interrupts.

## Safety

| | |
|---|---|
| Free | Reading/writing inside `workspace\`, web search/fetch, PDFs, ComfyUI, read-only shell commands |
| Asks first (`y` / `n` / `a` = always this session) | Deleting, files outside the workspace, other shell commands, Python, mouse/keyboard, browser clicks/typing, launching apps, scheduling |
| Never | `.env`, keys, `.ssh`, credential files; destructive commands (diskpart, format, bcdedit, …) |
| Scheduled runs | Nobody is there to approve, so anything that needs approval is refused |

Every prompt, tool call and approval decision is logged to `logs\audit.jsonl`.

## Tools

| Area | Tools |
|---|---|
| Files | list_dir, read_file, write_file, edit_file, copy_path, delete_path |
| Shell | run_powershell, run_python |
| Web | web_search, fetch_url, download_file |
| Desktop | list_windows, screenshot, focus_window, mouse_click, type_text, hotkey |
| Browser | browser_open / read / click / fill / screenshot / close (Playwright Chromium) |
| Apps | open_with_default_app, launch_app |
| PDF | create_pdf (Markdown → PDF with tables and images) |
| ComfyUI | comfy_status, comfy_list_models, comfy_txt2img, comfy_run_workflow (API-format JSON) |
| Schedule | schedule_task, list_scheduled_tasks, delete_scheduled_task (Windows Task Scheduler) |
| Memory | remember, recall |

## Customize

- **Personality:** edit `persona.md`.
- **Settings:** copy `config.local.example.yaml` to `config.local.yaml` (git-ignored) and override
  model, context length, workspace, allowed folders, ComfyUI URL/checkpoint.
- `reasoning_effort: none` is fastest; `low`/`medium` make her think more before acting.

## Performance tips

- The launcher loads the model with `--parallel 1`. LM Studio's default of 4 parallel slots (or `--gpu max`)
  can push a 35B model off the GPU and make it ~50× slower.
- Before loading the model and after each image job, Mochi asks ComfyUI to free VRAM.

## Limitations

- The default model has no vision, so Mochi can take screenshots but not see them. Browser tools (page text) are more reliable than desktop clicking.
- Scheduled tasks run only while the user is logged on.

## Tests

```powershell
.venv\Scripts\python.exe -m pytest              # offline: sandbox, approvals, shell policy, PDF, memory
.venv\Scripts\python.exe -m pytest -m live -s   # web, browser, desktop, ComfyUI, Task Scheduler
.venv\Scripts\python.exe -m pytest -m e2e -s    # real LLM, every approval denied
```

## License

MIT
