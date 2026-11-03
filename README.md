# Silentanator

Windows screenshot and typed-question study-notes app with image attachments, screenshot batches, a setup app, and a silent runner.

**[Download the Windows installer](https://github.com/Hola3Dprint/Silentanator/releases/latest/download/Silentanator-Setup.exe)** · [All releases](https://github.com/Hola3Dprint/Silentanator/releases)

## Install

Download **Silentanator-Setup.exe**, open it, and click **Install**. It installs for your Windows account without administrator access, adds Start menu shortcuts and a desktop Setup shortcut, and registers an uninstaller in Windows Settings. Python, the app libraries, and the official Codex CLI are included. Windows 10/11 x64 is required.

In **Silentanator Setup**, choose your notes file, click **Sign in to Codex** to sign in with your own ChatGPT account, then **Check connection** and **Save & run**. No credentials are included in the download. Word is optional for generating notes; use a `.docx` reader to open them.

The **Codex model** dropdown loads automatically from the signed-in account's Codex catalog. It shows screenshot-compatible models and the recommended model, with **Codex default** available at all times. **Refresh models** reloads the catalog; signing in or checking the connection refreshes it too. Refreshing never changes your selection. Previously saved custom model IDs are retained if they are not in the latest catalog. Discovery uses Codex's local app-server model-list interface and does not send a solve request or require an API key.

Each action hotkey has a **Record…** button: click it, hold your modifiers, and press a key. Escape or Cancel keeps the current shortcut. The recorder rejects duplicate shortcuts and reserved batch keys. Recording is active only while that dialog is open; the runner temporarily releases its global shortcuts so recording cannot trigger a capture. Save and restart the runner to apply changes. Manual shortcut entry remains available.

Use **Use existing…** to select a `.docx` full of notes and add to it, or **New…** to choose a new file.
Existing text, tables, pictures, headers, footers and other sessions are preserved. Before updating an
existing document, the app saves a timestamped copy under `%LOCALAPPDATA%/Silentanator/backups`.
Setup also accepts a reference folder and additional reference files (browse or paste one full path per line).
Save and restart the runner to apply changed references; a new session starts if the references changed.

Close the runner with Ctrl+Alt+Q before installing an update. Uninstalling removes the app and its shortcuts while keeping your notes, local session screenshots, settings, and Codex sign-in. You can remove that separate personal data yourself if desired. The installer is not code signed, so Windows may display a publisher/reputation warning.

## One-click updates

Click **Update from GitHub** in Setup or Live activity. It checks the latest stable release of
`Hola3Dprint/Silentanator`, downloads the official installer, and verifies its size, published SHA-256
checksum and GitHub asset digest before changing the installation. No GitHub sign-in is needed.
If the current version is already the latest (or newer), it reports that without reinstalling.

When an update is ready, open app windows close gracefully. An active solve finishes first; unsent
question drafts, attachments, pending screenshot batches and unsaved Setup fields are preserved.
The separate installer waits for the app to exit, applies the existing upgrade/rollback procedure,
then restarts the runner or Setup as appropriate. Notes, saved settings, references and Codex sign-in
are retained. Unsaved form edits are restored without being saved as configuration automatically.
Download/verification errors leave the current app running. The last installation result is stored in
`%LOCALAPPDATA%/Silentanator/updates/last-update.json`.

Updates happen only when requested. Install v1.3.0 once to add the button; future versions can be
installed through it. The installed runner also supports `Silentanator.exe --update`, which invokes
the same update-button action. Source checkouts and unmanaged portable folders are not overwritten.

## Run

For a portable build, run `dist/SilentanatorSetup/SilentanatorSetup.exe`, check the connection, choose the Word output, and select **Save & run**. Keep the entire distribution folder together. The bundled official Codex CLI uses your ChatGPT sign-in; the app does not read tokens or automate the ChatGPT website. Requests consume the account's Codex allowance, not a separate API balance.

Defaults:

| Action | Hotkey |
| --- | --- |
| Capture foreground window and solve | Ctrl+0 (top row or numpad zero with Num Lock on) |
| Start a batch of N screenshots | Ctrl+2 through Ctrl+9 (top row or numpad with Num Lock on) |
| Show/hide only the question text box | Ctrl+Alt+T |
| Show/hide live activity | Ctrl+Alt+0 |
| Stop runner | Ctrl+Alt+Q |

Setup lets you change capture, activity, text-box and exit hotkeys. Windows reserves the keys while running, so Ctrl+0 will no longer reset browser zoom. Conflicting hotkeys cause a startup error recorded in `%LOCALAPPDATA%/Silentanator/status.json`.

Setup can disable the Ctrl+2…9 batch hotkeys if another app needs them. These count shortcuts are
reserved while enabled; choose different shortcuts for capture/activity/text/exit.

### Typed questions, charts, and diagrams

Show Live activity with Ctrl+Alt+0. Type or paste a question, optionally click **Attach images…** to
add one or more charts, diagrams, or other images, and click **Solve** (or Ctrl+Enter). Image-only
attachment requests work too. Text and all attached images are sent as one input. Supported images
are PNG, JPEG, WebP, BMP and GIF (first frame). Original files stay unchanged. A text-only request
does not take a screenshot. Submitted typed questions and images are saved in the current session.
After a successful save the submitted draft and attachment list are cleared.

For just the text box, press **Ctrl+Alt+T**. Type your question and press **Ctrl+0** to include a
screenshot automatically, or press **Esc** to hide the box and select a different problem window
before capturing. The popup returns focus to the window you were studying and stays synced with
the main question form. **Ctrl+Enter** sends text without taking a screenshot. Any attached images
also join a normal screenshot request. The draft stays available if the request fails.

Solutions request detailed numbered work: knowns and unknowns, assumptions, governing formulas,
algebraic transformations, unit conversions, substitutions, intermediate arithmetic, answers and checks.

The solver automatically determines for each question whether its statement, course method, or mathematical
structure requires iteration. When needed, notes show the update rule, initial guess/bracket, each computed
iteration, residual/error and convergence test. Given course methods, starting values and tolerances take
priority; otherwise the solver labels its choices as assumptions. Direct questions use direct methods.
No iteration setting or checkbox is required.

### Screenshot batches

Press Ctrl+2 to enter two-picture mode, Ctrl+3 for three, and so on through Ctrl+9. Choosing a count
does not take a screenshot. Select each problem window and press Ctrl+0 once per picture. For example,
**Ctrl+2 → Ctrl+0 → Ctrl+0** captures two pictures and sends them together. Repeating the count
shortcut only shows progress. Nothing is sent until the entire batch is collected; then all its
images are submitted together as one multipart problem or multiple problems.
Any typed draft and attached images already in the question form join that batch. For 10–99 pictures, enter the count
in Live activity and click **Start batch**, then select each problem and press the capture hotkey.
**Cancel batch** discards it from solver context without sending its pictures or changing earlier notes.
Pending batches, their optional typed question, and their progress survive a restart. Saved cancelled
image files remain local, like other session screenshots. Larger batches use more Codex allowance.

The corner dot stays on for the entire time the runner is running. A half-second refresh restores
its visibility and topmost position after hiding or minimization without taking keyboard focus.

The hotkey listener runs on its own thread so the GUI cannot consume its messages. Every capture hotkey appears in the activity log. As a fallback, click **Capture in 3 seconds** and select the problem window before the countdown ends. The activity window minimizes during the countdown and returns after capture.

Run mode starts silent by default: no activity window, taskbar entry, tray icon, or notifications. A small dot in the bottom left corner stays visible throughout startup, capture, solving, saving, and error states: green ready, amber working, red error. It is always on regardless of notification settings. Ctrl+Alt+0 shows or hides the live activity window without hiding the dot. Setup can change the startup mode and notification preference. Its process name is `Silentanator.exe` in Task Manager. Use Ctrl+Alt+Q or Task Manager to stop it; when activity is visible, closing that window or clicking **Stop and exit** also stops the runner. There is no automatic startup or restart after termination.

The optional live activity window shows a screenshot preview, timestamped log, progress indicator, session notes, and errors. It reports capture, sign-in, request submission, waiting, equation conversion, saving, and opening the document. While waiting for Codex it updates the elapsed time every five seconds; this is request status, not a stream of model reasoning. Silent mode does not prevent the requested Word document from opening after a successful save.

Only a capture hotkey or the countdown button takes a screenshot. Choose the active window or primary monitor; avoid capturing unrelated private content. Select the problem window before pressing the hotkey. Capture is blocked while a request is in progress. The activity window and notification are hidden during capture; activity returns only if silent mode is off. The corner dot remains visible even during capture. Session screenshots are retained under `%LOCALAPPDATA%/Silentanator/sessions` and sent to OpenAI with each new image so the solver can use the full session context. Codex/provider retention policies still apply. No images are embedded in the notes.

## Notes

### Reading and generating charts

Capture or attach a clear chart image with its axes, ticks, units, and legend visible. Ask for a coordinate, intersection, slope, area, or interpolation in the question box. The solver checks the scale and explains its method; values read from an image are labeled estimates with sensible precision, and unclear or missing data must be called out.

When you ask for a plot or a chart is useful to the solution, the app generates it locally and embeds it in Word. Supported plots are numeric line, scatter, grouped bar, and mathematical function curves, with linear/logarithmic axes, optional axis limits, inverted y axes, and labeled points. Bar plots use a linear x axis. Examples: `Plot y=x^2 from 0 to 4 and label the point (2,4).` Or: `Read the value at x=2.5 from this chart, show the interpolation, and plot the estimated point.`

The notes include captions, sources, approximation notes, and a coordinate table for highlighted points. **Open charts** in the activity window opens `%LOCALAPPDATA%/Silentanator/charts`, containing PNG images, CSV data, and JSON chart specifications. CSV data distinguishes provided, calculated, and estimated values. Function curves are sampled locally from a restricted mathematical expression; model-supplied Python code is never executed. Undefined sampled values are left as gaps. The charts are embedded images, not native editable Word chart objects; their underlying data is exported separately.

### Course context

In Live activity (Ctrl+Alt+0), paste a path into **Reference folder** and press Enter.
Use a course folder or a parent folder containing all your materials; subfolders are searched
recursively. Paths copied with quotes from Explorer work too. Workspaces and generated output
folders are excluded. Changing folders starts a new session and preserves earlier notes.
The folder path is restored after restarting. Leave the box blank to solve from screenshots only.
Invalid paths are reported without changing the current session or starting a capture.

For a course solve, the app first identifies search terms from the problem image using Codex,
then searches a local text index of that course's PDFs, DOCX, PPTX, Markdown, text and HTML files.
It sends up to 18 relevant excerpts (about 36,000 characters) with the screenshots to Codex.
The solution is instructed to follow course methods and notation and cite the filenames and
PDF pages or slide numbers actually used. It labels a general method when the excerpts do not
support a course-specific approach. This retrieval step adds a second Codex request per capture.

The index lives in `%LOCALAPPDATA%/Silentanator/course-cache` and refreshes when source files
change. Course files are never modified. Duplicate files are indexed once. Scanned/image-only
pages, encrypted/corrupt files, and files over 60 MB may be unavailable; extraction warnings
appear in activity. OCR is not included. Course images/diagrams are not extracted from PDFs.
Selected excerpts are sent to OpenAI through your signed-in Codex account; the full course
folder is not uploaded. Verify the cited method and answer against your original materials.

The default file is `Documents/Notes.docx` with the visible title **Notes**. Captures in the same session share all prior images and the latest notes. The solver returns complete updated session notes: it continues related problems, corrects earlier assumptions when more information appears, and adds sections for new problems. That session's Word content control is replaced in place, preserving earlier sessions and other document content. Equations remain native editable Word equations (OMML), converted from LaTeX.

The current session's image history and latest answer are saved locally and restored after a restart. **New session** clears the solver's context for subsequent captures and starts a new section in the same file; earlier notes and saved sessions remain. It does not delete session images. Notes created before session support remain in the document; their original screenshots are not available as context. Longer sessions resend more images and use more of the Codex allowance.

After saving, the document automatically opens in the default `.docx` application (Word if associated). If Microsoft Word has the document open, the app finds the exact file across Word instances, saves any edits, closes that document briefly to release its lock, updates it, and reopens it. Other Word documents are left open. Saving and closing happens before reading the file so saved manual edits outside the generated session are preserved. If Word cannot save (for example, a dialog is blocking it), the document stays open and the solution is kept for retry. If another application locks the file or Word cannot be connected to, close the document before retrying. Word need not be installed for document generation.

Completed responses awaiting save are stored under `%LOCALAPPDATA%/Silentanator/pending`. Recovery uses the latest available snapshot for a session so older pending responses cannot roll its notes back or duplicate them. Equation conversion errors also preserve the response for inspection; unsupported LaTeX may require correction. Model answers can be wrong; review them.

Settings are in `%LOCALAPPDATA%/Silentanator/settings.json`. Most recent status/error is in `status.json`; after Task Manager termination this may be stale. Restart the runner to apply setup changes. Trying to start a second runner does not stop the original.

## Development

Python 3.12+ on Windows. Run `./build.ps1` to install isolated dependencies and build both windowed executables, including the pinned official Codex CLI verified by SHA256. Run `./scripts/build_installer.ps1` with the .NET 8 SDK installed to build `release/Silentanator-Setup.exe` and `SHA256SUMS.txt`. The installer is self contained; the destination computer does not need .NET installed. Dependency license texts are included in the application folder. Without packaging:

```powershell
./.venv/Scripts/pythonw.exe -m silentanator.setup
./.venv/Scripts/pythonw.exe -m silentanator.runner
./.venv/Scripts/python.exe -m unittest discover -s tests -v
```

The app runs `codex exec` with image input, structured output, ephemeral sessions, read-only sandbox, and approvals disabled. It ignores user Codex configuration to avoid inheriting custom providers, hooks, or MCP servers, and checks that authentication reports ChatGPT rather than an API key. The prompt requests no tools. This is a Codex-backed solver, so model availability and behavior follow the installed Codex version. See [official non-interactive documentation](https://learn.chatgpt.com/docs/non-interactive-mode).
