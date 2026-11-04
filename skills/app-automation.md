name: app-automation
description: Operate a Windows desktop app without the mouse (UI Automation), e.g. fill fields, press buttons, read results

1. If the app isn't open: launch_app (or open_with_default_app for a file), then wait 2-3 seconds.
2. list_windows to get the exact window title.
3. app_inspect(window, filter=...) to find controls: note control type, name and automation id.
4. app_set_text for inputs, app_click for buttons/checkboxes/menu items (works in the background, no mouse).
5. app_read to read results/labels and confirm the action worked.
6. Only if UI Automation can't reach a control: screenshot (vision models) + mouse_click(from_screenshot=true).
7. When done, tell the user what you did; close the app only if you opened it and the user agrees.
