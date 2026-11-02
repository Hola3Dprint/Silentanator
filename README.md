# Silentanator

Windows hotkey screenshot-to-study-notes app with a setup app, silent runner, and optional live activity window.

**[Download the Windows installer](https://github.com/Hola3Dprint/Silentanator/releases/latest/download/Silentanator-Setup.exe)** · [All releases](https://github.com/Hola3Dprint/Silentanator/releases)

## Install

Download **Silentanator-Setup.exe**, open it, and click **Install**. It installs for your Windows account without administrator access, adds Start menu shortcuts and a desktop Setup shortcut, and registers an uninstaller in Windows Settings. Python, the app libraries, and the official Codex CLI are included. Windows 10/11 x64 is required.

In **Silentanator Setup**, choose your notes file, click **Sign in to Codex** to sign in with your own ChatGPT account, then **Check connection** and **Save & run**. No credentials are included in the download. Word is optional for generating notes; use a `.docx` reader to open them.

Close the runner with Ctrl+Alt+Q before installing an update. Uninstalling removes the app and its shortcuts while keeping your notes, local session screenshots, settings, and Codex sign-in. You can remove that separate personal data yourself if desired. The installer is not code signed, so Windows may display a publisher/reputation warning.

## Start

For a portable build, run `dist/SilentanatorSetup/SilentanatorSetup.exe`, check the connection, choose the Word output, and select **Save & run**. Keep the entire distribution folder together. The bundled official Codex CLI uses your ChatGPT sign-in; the app does not read tokens or automate the ChatGPT website. Requests consume the account's Codex allowance, not a separate API balance.

Defaults:

| Action | Hotkey |
| --- | --- |
| Capture foreground window and solve | Ctrl+0 (top row or numpad zero with Num Lock on) |
| Show/hide live activity | Ctrl+Alt+0 |
| Stop runner | Ctrl+Alt+Q |

Setup lets you change all hotkeys. Windows reserves the keys while running, so Ctrl+0 will no longer reset browser zoom. Conflicting hotkeys cause a startup error recorded in `%LOCALAPPDATA%/Silentanator/status.json`.

The hotkey listener runs on its own thread so the GUI cannot consume its messages. Every capture hotkey appears in the activity log. As a fallback, click **Capture in 3 seconds** and select the problem window before the countdown ends. The activity window minimizes during the countdown and returns after capture.

Run mode starts silent by default: no activity window, taskbar entry, tray icon, or notifications. A small dot in the bottom left corner stays visible throughout startup, capture, solving, saving, and error states: green ready, amber working, red error. It is always on regardless of notification settings. Ctrl+Alt+0 shows or hides the live activity window without hiding the dot. Setup can change the startup mode and notification preference. Its process name is `Silentanator.exe` in Task Manager. Use Ctrl+Alt+Q or Task Manager to stop it; when activity is visible, closing that window or clicking **Stop and exit** also stops the runner. There is no automatic startup or restart after termination.

The optional live activity window shows a screenshot preview, timestamped log, progress indicator, session notes, and errors. It reports capture, sign-in, request submission, waiting, equation conversion, saving, and opening the document. While waiting for Codex it updates the elapsed time every five seconds; this is request status, not a stream of model reasoning. Silent mode does not prevent the requested Word document from opening after a successful save.

Only a capture hotkey or the countdown button takes a screenshot. Choose the active window or primary monitor; avoid capturing unrelated private content. Select the problem window before pressing the hotkey. Capture is blocked while a request is in progress. The activity window and notification are hidden during capture; activity returns only if silent mode is off. The corner dot remains visible even during capture. Session screenshots are retained under `%LOCALAPPDATA%/Silentanator/sessions` and sent to OpenAI with each new image so the solver can use the full session context. Codex/provider retention policies still apply. No images are embedded in the notes.

## Notes

### Course context

In Live activity (Ctrl+Alt+0), choose **Course for this session**. The course list comes from
`Documents/StudyFlow`; change the parent folder in Setup under **Course references**.
Each course is a direct child folder. Workspaces and generated output folders are excluded.
Changing course starts a new session and preserves earlier notes. The selected course is restored
after restarting. Choose **Screenshot only** to solve without course references.

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
