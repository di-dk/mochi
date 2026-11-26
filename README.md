<p align="center"><img src="assets/mochi_small.png" width="240" alt="Mochi, an anime girl with a pink bob in a pink dress and frilly apron, holding cake and tea"></p>

# 🍡 Mochi — a cute, careful local AI agent for Windows and Linux

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

## Linux

Mochi also runs on Linux (tested on Pop!_OS / COSMIC with Python 3.12). It does not need LM Studio there: it talks to
any OpenAI-compatible server, such as [Ollama](https://ollama.com).

```bash
git clone https://github.com/di-dk/mochi
cd mochi
./setup.sh                 # venv, packages, Chromium, offline tests, `mochi` command + app-menu entry
```

Then point her at a model server (Ollama example):

```bash
ollama pull qwen3:14b                                   # any model that supports tool calls
cp config.linux-ollama.example.yaml config.local.yaml   # edit llm.model to match `ollama list`
OLLAMA_CONTEXT_LENGTH=32768 ollama serve                # Ollama's default context is too small for her tool prompts
mochi                                                   # chat, or: mochi "task", mochi --gui
```

**Settings.** `llm.backend` is `auto` by default: if LM Studio's `lms` is installed she uses it as on Windows, otherwise
she only talks to `llm.base_url`. Set `backend: openai` to force that. For a hosted API, put the key in an environment
variable and name it in `llm.api_key_env` (the key is never stored in a file).

**What works.** Everything except what needs Windows itself: files, web, the headless browser, documents, images,
ffmpeg media, ComfyUI, skills, memory and the safety rules, plus Linux versions of the desktop tools. The shell tool is
`run_shell` (bash) instead of `run_powershell`; read-only commands such as `ls`, `pwd` and `date` run directly,
everything else asks first.

| Tool | How it works on Linux | Needs |
|---|---|---|
| `list_apps`, `launch_app` | the apps in your menu (`.desktop` files), started with `gio launch` | nothing extra |
| `schedule_task` and friends | systemd user timers (`systemctl --user list-timers 'mochi-*'`); run while you are logged in | systemd |
| `list_windows`, `app_inspect`, `app_read`, `app_click`, `app_set_text`, `app_close`, `focus_window` | accessibility (AT-SPI), no mouse needed, works on Wayland and X11 for apps that expose accessibility (GTK, Qt, Electron/Chromium with accessibility on) | `sudo apt install python3-gi gir1.2-atspi-2.0 at-spi2-core`, and `setup.sh` run after that |
| `mouse_click`, `type_text`, `hotkey`, `app_keys` | a virtual keyboard and pointer through `/dev/uinput`; they always ask first. `type_text` sends US-layout key codes, so it refuses other keyboard layouts (use `app_set_text`) | write access to `/dev/uinput` |
| `screenshot` | `grim` (Wayland), or `gnome-screenshot` / `spectacle` / `scrot` | `sudo apt install grim` |
| clipboard, notifications, speech | `wl-clipboard` or `xclip`, `notify-send`, `spd-say` or `espeak-ng` | install the one you want |

A tool is only offered to the model when its backend works on your machine; the rest are left out. Mouse and
keyboard control on Wayland depends on your compositor, so check a first click with a screenshot. Use
`browser_screenshot` for vision on web pages.

Her own window (`mochi --gui` / `mochi-window`) opens in your browser; install `pywebview` for a native window.
`./setup.sh --uninstall` removes the command and menu entry.

## Files and photos in the chat

She can show you any file. Images and videos appear as small thumbnails; click one to see it big (videos play with
a seek bar). Audio plays in the chat, and PDFs, documents, archives and every other type get a download card. Each card
shows the file's path with a **copy path** button. Ask her things like "show me the picture you just made", "find my
latest video" or "send me that PDF": `find_my_files` looks through her workspace (newest first, by kind, name or age)
and `share_file` puts the result in the chat. A file outside her workspace is copied into `workspace/shared` first
(she asks before reading it), and credential files are never shared.

`image_edit` edits photos without touching the original: auto-orient, crop, rotate, flip, resize, brightness, contrast,
saturation, sharpness, blur, grayscale, sepia, invert and auto-contrast, saved as png/jpg/webp/gif/bmp/ico. The result
appears in the chat.

## How she looks, and drawing herself

Her exact look (rose-pink bob with raspberry tips and straight bangs, big rose-pink sparkly eyes, pink maid dress with a
white collar and aqua trim, white frilly apron with two pink-bow pockets, bold-outline pastel anime style) is written
once in `agent/identity.py` and is part of her instructions in every chat. She describes herself only with it. When she is
asked to draw, show or change herself she uses `draw_myself`: it redraws her from her own portrait
(`assets/mochi.png`, or the close-up for a mood) with Qwen-Image-Edit in ComfyUI and an identity lock, so her face, hair and
outfit stay the same while only the scene changes ("in a winter coat in the snow", "as a little witch", "laughing").
A plain text-to-image model has never seen her, so `comfy_txt2img` refuses self-portraits and points her to `draw_myself`.
Change her look by replacing the pictures in `assets/` and editing `agent/identity.py`.

## Teaching herself new things

When she does not know how to do something she does not give up: she follows the built-in `learn-new-skill` recipe.
She looks for a saved skill, researches on the web (retrying other search engines if one fails), tries the smallest
safe test in her workspace, verifies the result, and then saves what worked with `save_skill` (steps, settings and the
URLs she learned it from). If she says "I learned: ...", she has to have saved it; she is nudged if she did not. Ask for
it directly: "you have no skill for this, learn how to get the ISS position yourself". Anything risky still asks you first.

**Skills from git.** She can also learn skills other people have written, in the same `SKILL.md` format Claude uses:
`list_git_skills` browses a public GitHub repository (default: Anthropic's `anthropics/skills`, or any
`owner/repo` or github.com URL) and `import_skill` copies one into her skills. Because a skill from a repository is
someone else's text that will steer her:

- **every skill is scanned first** with NVIDIA SkillSpector (see below), before you are even asked;
- **you approve every import**: it cannot be auto-allowed, set to "always", or done in an unattended run, and the
  approval shows the source, the size, the scan result and warnings for risky content (piping downloads into a shell,
  `sudo`, credential files, "ignore previous instructions", skipping approvals);
- only text is copied (no binaries, nothing large, nothing outside the skill's own folder), and scripts are stored as
  plain files: running one still goes through the normal shell / Python approval;
- the skill is marked as imported, with its source link, and never overrides her safety rules.

For ComfyUI she can discover what is installed (`comfy_list_models kind=all`) and look up nodes (`comfy_node_info`),
edit images and animate them from ready templates in `workflows/`, or build and save new workflows herself (skills
`comfy-image`, `comfy-edit-image`, `comfy-animate-image`, `comfy-new-workflow`).

## Every skill is scanned before it is installed (NVIDIA SkillSpector)

Skills are instructions plus scripts that run with your trust, and public ones are not always safe. So she never
installs or trusts one without checking it with [NVIDIA SkillSpector](https://github.com/NVIDIA/SkillSpector) (Apache-2.0,
71 vulnerability patterns: prompt injection, data theft, privilege escalation, supply chain and more). `setup.sh` /
`setup.ps1` install it into its own environment, `.skillspector/` (it needs Python 3.12 or 3.13).

- **`import_skill`** fetches the skill into a throw-away folder and scans it **before** asking you or writing anything.
  Verdict `DO NOT INSTALL` (score 51+): refused outright, no question asked and no way for her to override it.
  `CAUTION` (21 to 50) or `SAFE`: you are asked, with the score and the findings shown.
- **Fail closed**: if the scanner is missing, crashes, times out or could not inspect a script, the skill is **not**
  installed (`skillspector.require: true`). Partly inspected documentation is only noted.
- **Tamper-proof**: the scan result and a fingerprint of the skill and its files are stored with it. If anything changes
  afterwards, or an imported skill has no scan, she will not read or follow it.
- **Her own skills** (from web research) are scanned before `save_skill` writes them, and refused if they are dangerous.
- **`scan_skill`** checks any skill without installing it: a saved one, a workspace folder or a GitHub skill.
- **Deeper review (optional)**: `deep=true` (or `skillspector.llm: true`) also runs SkillSpector's LLM stage on your local
  Ollama model (nothing leaves the PC, 1 to 2 minutes). It is advisory only: small local models raise false alarms
  (it called a harmless skill dangerous in testing), so it can never block or approve by itself.
- It is strict: in testing, Anthropic's `docx` skill scored 64/100 and was refused (it runs `rm` and chains shell
  commands), while `pdf` scored 7 (`CAUTION`). If you accept that risk for skills you trust, set
  `skillspector.on_danger: ask` in `config.local.yaml`: then *you* are asked, with a warning, instead of it being refused.
  She can never make that choice.

A scan lowers the risk, it does not remove it: static analysis can miss things. Skills you do not need, you should not install.

## Many languages, and Nepali

She answers in the language you write in and switches when you do (`agent.language: auto`; set a fixed language such as
`Dutch` or `Japanese` in `config.local.yaml` to always use it). Her name, her look and her warm personality stay the same
in every language, and she uses the right politeness level for the language (tu/vous, du/Sie, u/je, तपाईं/तिमी...).
Skills: `work-in-language` (reply, research and write in a language), `translate-text` (files and documents, keeping the
structure and a glossary), `nepali` and `nepal-info`.

What the tools do with other scripts:

| Script | PDF | Word | Notes |
|---|---|---|---|
| Western European, Cyrillic, Greek, Central European (ł, ő, ș...) | yes (bundled DejaVu Sans) | yes | |
| Chinese, Japanese, Korean | yes, can be mixed with other scripts | yes | uses the PDF viewer's own CJK fonts (Korean needs one on the viewing computer) |
| Arabic, Hebrew (right to left) | yes, shaped and right-aligned | yes, marked right-to-left | |
| Nepali, Hindi (Devanagari), Thai and other complex scripts | yes, printed with the browser engine (Chromium) | yes | needs `playwright install chromium`; without it the tool says so and suggests Word |

`speak` takes a language code (`ne`, `nl`, `fr`, ...) and uses a matching voice when one is installed. The chat window
shows any script and right-to-left text. Its buttons and labels are still in English.

**Nepali (नेपाली).** She writes Devanagari by default, understands Romanized Nepali, uses तपाईं with you, and checks rare
words instead of guessing (Wiktionary, ne.wikipedia). For Nepal she has the Bikram Sambat calendar (`nepali_date`:
AD to BS and back, today's date, month and weekday names; it uses the `nepali-datetime` package, which I checked against
the Nepali New Year dates and Bijaya Dashami 2082) and Nepali number styles (`nepali_format`: Devanagari digits, lakh/crore
grouping, `रु. १२,३४,५६७`), plus local units, festivals (always looked up, never guessed) and money. Translations go through `translate_text`, a dedicated pass with a checked glossary (`skills/nepali-glossary.md`), and
today's Nepali date is placed in front of her fresh each time (she used to copy an example date). Honest limits: her
Nepali is only as good as the model behind it. In my tests a 14B Qwen model managed everyday sentences but garbled harder
ones, while `gemma3:12b` as the translator (`llm.translator_model: gemma3:12b`, `ollama pull gemma3:12b`) was clearly
better on 4 of 5 new sentences and 2 to 4 times faster; it still makes mistakes (it misread "happy to meet you" and once put a
stray Latin letter in a word, which she now catches and retries). For anything official, have a native speaker check it.

## ComfyUI, made reliable

She knows what her ComfyUI can really do and has one call for each job, so a small model cannot mis-assemble a workflow:

- **`comfy_capabilities`**: every installed model grouped by purpose, which tool covers it, which still needs a workflow (video
  models are not checkpoints), and the GPU. "READY" is only printed when the template really validates.
- **`comfy_video`**: "make a dancing cat video" is one call (Wan 2.2 text-to-video; with `image=` it animates a picture). 1 to 5
  seconds, square, landscape or portrait, about 30 to 90 seconds. It shows the video in the chat.
- **`comfy_check`**: tests every workflow template against the installed nodes and model files before running anything.
- **`comfy_start`**: starts ComfyUI (local only, after asking you) when it is not running.
- **GPU memory**: Ollama keeps her language model on the GPU, which starves ComfyUI. It is unloaded before a job and loads again by
  itself (`comfyui.free_llm_before`). If a video still runs out of memory it is retried once, smaller.
- **Errors say what to do**: out of memory, a wrong model name, a missing node, a wrong template key and a missing input picture each
  get advice instead of a stack trace. The skill `comfyui-expert` is her playbook.

Not everything installed has a ready workflow yet: music (ACE-Step), Qwen-Image text-to-image, LTX video with sound and sound
effects show up as "needs a workflow", and she builds those with `comfy-new-workflow`. No one can promise "never fails", so there is
an opt-in test against your real ComfyUI: `MOCHI_LIVE_COMFY=1 pytest tests/test_comfy_expert.py`.

## Her voice, talking to her, and auto mode

- **Voice** (🔊 in the chat window): she reads her replies aloud sentence by sentence while she writes them. **Talk** (🎙):
  hands-free conversation. You speak, pause, and she answers in her voice. Both run locally on the CPU (Kokoro for speaking,
  Whisper for listening), so nothing leaves your PC and the GPU stays free for the language model. `./setup.sh` downloads the
  voice files (about 840 MB) into `models/voice`. The microphone works in the browser window (it needs your permission);
  headphones avoid her hearing herself. Her voice is a blend set in `config.local.yaml`:
  `voice: {blend: "af_bella:0.75,jf_tebukuro:0.25", speed: 0.97, pitch: 1.06}`. Kokoro has no Asian-accented English voice,
  so the Japanese part of the blend only softens the tone. Say her name "MOH-chee": that is handled for you.
- **Auto mode** (⚡ in the header, or `/auto on` in the terminal): she works on her own without asking about each action. She
  still asks before deleting, importing a skill, or typing into sensitive windows (terminals, password prompts), and scheduled
  unattended runs never get auto mode. Add more categories to keep asking about with `approvals.auto_mode_keep_asking`.

## Pet mode: a little chibi Mochi on your desktop (Linux, optional extra)

`./mochi --pet` puts a small animated chibi Mochi on top of everything on your screen. The normal chat window is unchanged: pet mode is
an extra, and the chat window has a 🐾 Pet button to bring her back from it.

- **She lives on your screen:** she wanders along the screen, sits on her bed or armchair and naps when you leave her alone, reads a book, has tea.
- **Drag and poke:** drag her anywhere (the spot you grab stays under the mouse; she reacts differently if you grab her head, body or feet) and
  she stays where you drop her. A single click pokes her (headpat, tickles, "my feet!"). Double-click, or right-click > Type to her, to talk.
- **She talks back in a speech bubble.** Approval questions appear there too, with Yes / Always / No buttons, and a button opens the full chat.
- **Right-click menu:** stay where I put her / wander, her voice, the microphone (hands-free talking), auto mode, size (S M L XL), take a nap,
  open the full chat, hide her, quit.
- **Set-up:** pet mode needs the GTK4 layer-shell library. `pet/install_layer_shell.sh` builds it into `~/.local` (its first lines tell you the one
  `sudo apt install` it needs). Her pictures and animations are not in git (about 25 MB): download `mochi-pet-animations.zip` from the release and
  unzip it in the Mochi folder (it creates `pet/sprites` and `pet/anim`), or make your own with ComfyUI: `python -m pet.make_sprites` then
  `python -m pet.make_anim` (stop Ollama first; each clip takes about half a minute). Without them she is drawn with a simple placeholder.
- **Settings** are in `~/.config/mochi-pet.json` (`scale`, `walk`, `voice`, `sleep_after` in seconds, `emoji`). If something misbehaves, `logs/pet-debug.log`
  records what a drag does.

## Better memory, asking, backup model, MCP tools, wake word

- **Memory search.** `recall` now searches her saved notes AND everything said in past chats, ranked by how well the words match (any
  script, Nepali too) with newer things boosted. Optional: set `memory.embed_model` (an Ollama embedding model, e.g. `nomic-embed-text`,
  pulled by you) in `config.local.yaml` and meaning-based matching is mixed in ("my sister" finds "Sita turns 30"). All local.
- **She asks instead of guessing.** The `ask_user` tool lets her stop and put ONE short question to you when a detail she needs is missing
  (with numbered options if there are some). Work already done stays done and your answer continues the task.
- **Backup model.** If the main model server is down, she can switch to a backup for the rest of the session and tells you:
  `llm: {fallback: {base_url: "http://127.0.0.1:11434/v1", model: "some-model", api_key_env: "OPTIONAL_ENV_NAME"}}`.
- **MCP tools.** She can use tools from MCP servers that YOU list in `config.local.yaml` (`mcp: {servers: {name: {command, args, env, trust}}}`,
  see the top of `agent/mcp_client.py`). An MCP server is a program that runs with your permissions, so: nothing is started, downloaded or
  installed unless you wrote it in the config; every call asks you first (even in auto mode) unless you set `trust: auto` for that server;
  its tool names, descriptions and results are treated as third-party text, never as instructions; a server whose tool list changes
  after you first connected it is flagged; and it only gets the environment variables you list for it. `mcp_servers` shows what is connected.
- **Wake word.** In hands-free mode (🎙 Talk, or the pet's microphone) she now only reacts when you say her name: "Mochi, what is the weather?"
  After she answers you can keep talking for 25 seconds without it. Switch with the 👂 Wake button or the pet menu, or `voice.wake_word: false`.
- **Her browser works again.** Her own Chromium (`browser_open`, `browser_click`, ...) now runs on one dedicated thread. Before, every
  chat message ran on a new thread and the connection was dead after the first ("Playwright connection closed"). She also closes
  leftover copies of her own browser and restarts a dead one.

## Which version is running

The chat window shows it under her name (hover for details), the terminal banner shows it, and `mochi --version` prints it. A
development checkout says so, e.g. `v0.13.0 (development: 3 newer commits, abc1234, local changes)`. The number lives in
`agent/version.py` and matches the release tag.

## Tested on real tasks

`tools/battery.py` runs 22 realistic tasks against her real model in throw-away workspaces and checks the results: arithmetic and dates,
Python scripts, Excel, PDF, Word-free conversions, sorting and renaming files, summaries, invoices, translation, web research, Nepali
dates, memory, charts, emails, JSON, and ComfyUI pictures, edits, video and self-portraits. Routine approvals are granted; package
installs, sudo, deletes and anything outside the workspace are refused. Run it with `python tools/battery.py` (needs Ollama, the
internet and ComfyUI; results go to `logs/battery.jsonl`).

The first run passed 8 of 12 tasks; each failure became a fix, and the full 22-task run then passed 20, with the last two
failures fixed and re-checked on their own. What it found and what changed:

- **Arithmetic and dates done in her head were wrong** (135 days came out as 126; she guessed a weekday): new `calculate` and
  `date_math` tools (exact, safe), and the date tool always names the weekdays.
- **No way to move files**, so she faked it and claimed success: new `make_folder` and `move_path`; `copy_path` copies into folders.
- **Claiming success without checking**: she cannot finish while a file you named does not exist; a success claim after a failed or
  denied step, or after calling no tool at all ("I've remembered it"), is challenged once.
- **Invalid JSON** (Python quotes) written as ".json": the file tool refuses it with the reason.
- **A self-portrait for "a red dragon"**: `draw_myself` now refuses requests that are not about her.
- **Recipes for tools that are not installed** (a video studio) are never offered; `comfy_video` is used instead.
- **Search engines**: more engines are tried, Wikipedia summaries are the fallback, and a `web-research` recipe says to use official
  sources and never answer a current fact from memory.
- Data libraries (pandas, numpy, matplotlib) for `run_python`, and recipes `convert-files`, `data-analysis` and `web-research`.

It is a floor, not a promise: 22 tasks cannot cover everything, and a model can still misjudge something the checks do not see.

## Her moods

Her profile picture is a close-up that changes with how she feels: relaxed, happy, excited (a long task, or you
thanked her), thinking, working (while she uses tools), asking (she needs your OK), worried (something failed), sad
(you denied a request, stopped her, or a hard error) and sleepy (nothing happening for a couple of minutes). Click
the picture for the big version. The pictures are in `assets/expressions/<mood>.webp` (512 px) and
`<mood>_small.webp` (160 px); replace them with your own to change her look.

## Use

Double-click **Mochi** on the desktop, or in any terminal:

```powershell
mochi                                            # chat
mochi "make a PDF about the history of Brussels" # one-shot task
```

(Without the PATH step, use `.\mochi.cmd` from the Mochi folder.)

### Her own window

```powershell
mochi --gui        # or double-click mochi-window.cmd
```

A native chat window with her avatar, chat bubbles, a steady typewriter for every reply, collapsible tool steps,
pictures she makes, a model picker, a **Stop** button, and Allow / Always / Deny buttons for approvals. It is the
same agent with the same settings and safety rules as the terminal, which keeps working as before. You can keep
typing while she works. It uses `pywebview` (Edge WebView2, already part of Windows 11); without it she opens in
your browser. The window talks to a local server on 127.0.0.1 protected by a random per-run token.

**Saved chats.** Every conversation is saved (in `workspace/chats/`) and listed in the sidebar, grouped by day,
with search, rename and delete. Open an old chat and she remembers it: her own message history is restored, so you
can carry on without explaining everything again. Chats stay on your PC.

**Color themes.** The palette button in the window header switches between Auto (follows Windows), Mochi dark, Mochi light, Sakura, Lavender, Mint, Midnight blue, Ocean, Forest, Sunset and Graphite. Your choice is kept in `config.local.yaml` (`ui.theme`).

### Attaching files

Photos, videos, PDF, Word, Excel/CSV, text and code, audio and zip files all work.

- **Window:** the paperclip button, drag and drop anywhere, or paste an image.
- **Terminal:** type `@path` in your message (`@"path with spaces"` also works, and so does dragging a file into the
  terminal), or `mochi "what is in this?" --file photo.jpg`.

Files are copied into her workspace (`workspace/uploads/`) and summarised for her: photos and a few frames of each
video are shown to a vision model, PDFs, documents and spreadsheets are previewed, and she can open anything in
more depth with her tools. She cannot hear audio. Credential files are refused.

## Antivirus says Mochi is a trojan

Mochi is unsigned open-source software that runs scripts, drives your browser and controls windows, so some antivirus
programs are suspicious of it. The most common report is **`Trojan.Loader`** (seen with Malwarebytes) on the desktop
shortcut. That is a false positive on the *shortcut*, not on Mochi's code: older versions of `setup.ps1` made a
shortcut that started `cmd.exe` or Windows Terminal with a command line, which is a shape malware often uses.

Current versions create shortcuts that point straight at `mochi.cmd` / `mochi-window.cmd` with no arguments. If you
installed an older version, **run `setup.ps1` again** (it replaces the old shortcuts), or delete the two Mochi
shortcuts and launch with `mochi` / `.\mochi.cmd` / `.\mochi-window.cmd`.

If your antivirus still quarantines something:
- Look at which file it names. Everything Mochi runs is plain text you can read in this repository.
- If you trust the copy you downloaded, restore the item and allow only the Mochi folder (not whole drives), then
  report it as a false positive to the vendor so it stops happening for everyone.
- Do not switch your antivirus off. Mochi does not need that.

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
  `meme-maker`). Only the first 60 skills are listed to the model, so keep the total under that.
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
