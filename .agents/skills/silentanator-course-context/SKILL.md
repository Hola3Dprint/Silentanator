---
name: silentanator-course-context
description: Maintain and validate course-document retrieval in Silentanator, including per-session selection, local indexing, cited solving, and packaged Windows verification. Use for this repository's course-context features rather than general document questions.
---

# Silentanator course context

## Architecture and constraints

- `silentanator/course_context.py` accepts a pasted reference-folder path, recursively extracts source-labelled text, caches by file metadata, and retrieves bounded excerpts. The folder may contain one course or all materials. Keep the UI as a plain path box, not a course dropdown. `core.solve` uses a screenshot-only Codex query to obtain search terms before the final solve. Preserve the no-tools prompt, read-only sandbox, ChatGPT sign-in path, and credential isolation.
- Store selection in `StudySession` state, not a global course setting. Changing course starts a fresh session while preserving earlier notes. Restore selection across restarts. Existing sessions without a course remain screenshot-only.
- Setup may supply a folder and additional explicit files. Its reference revision applies changed defaults once on the next runner launch; subsequent restarts preserve session-specific choices. Setup displays current session references unless newer choices are waiting to apply. Test this synchronization when changing reference settings.
- Never alter source documents. Exclude generated Workspaces/output folders, avoid following reparse points, deduplicate content, and refresh changed/deleted sources. Keep filenames and PDF page/slide labels attached to every excerpt.
- State extraction gaps, especially image-only PDF pages, diagrams, encrypted files, and size limits. Do not equate extracted text with full document coverage. Cite only references actually used and distinguish general methods when retrieval is insufficient.
- Keep local course text and cache out of Git, release payloads, logs, and test fixtures. UI copy must explain that selected excerpts are sent to OpenAI.

## Validation

Run commands from the repository root with its virtual environment:

```powershell
./.venv/Scripts/python.exe -m unittest discover -s tests -v
./.venv/Scripts/python.exe -m tests.runner_smoke
git diff --check
```

Tests should cover source refresh/deletion, course isolation, citations/warnings, session restoration,
and the query-retrieval-final-solve boundary. For extraction changes, also exercise a real supported
document locally. Use a synthetic problem image for an authorized live solve, check the numerical
result and source citation, and generate native editable Word equations. Keep this evidence local.

Inspect the native UI after changing layout. Tk pack order can let an expanding notes pane hide
later controls: reserve bottom controls before allocating the remaining space to the notes.
Verify actual course selection writes the expected session state. Preserve and restore the user's
active-session pointer when doing disposable UI tests; do not capture unrelated desktop content.
For the folder box, verify quoted paths with spaces, Enter/focus-loss application, validation before
capture, blank input, and restart persistence. Focus the entry before generating a keyboard event
in Tk smoke tests; otherwise the key event may not invoke its binding.

## Mixed inputs and preservation

- Typed questions and attached chart/diagram images are one current input. Pass the current image count separately from prior session images, and keep typed-question history distinct from the current question. A text-only request must not capture the desktop or add a null `--image` argument.
- Batch hotkeys map Ctrl+2…9 to counts, including numpad aliases. Pending images and optional typed text persist separately from submitted image history. Do not invoke the solver before the target count is collected. Cancellation must never add pending images to solver context. Use the count box for larger batches, and prevent session/reference changes while collecting.
- Verify the complete hotkey path against synthetic problem windows: first capture records a pending batch without any answer/request; final capture submits all images and returns work for each question. Use separate QA notes and settings so real notes remain untouched.
- Existing Word files are append targets. Preserve manual paragraphs, tables, images, headers, footers and unrelated session controls; only replace the current generated session. Back up the exact saved original before every existing-file update and verify the backup bytes in tests.
- The corner indicator remains visible throughout the runner lifetime. Reassert visibility/topmost state without activating it; avoid repeatedly deiconifying an already visible Tk window, which can interfere with typing. Keep the indicator active during silent mode, owner minimization, capture and solving.
- Keep the question composer visible, with activity, notes and screenshot preview in tabs so larger inputs do not hide controls. Validate `tests.setup_smoke` as well as the runner smoke test after modifying Setup or mixed-input controls.

For an authorized Windows release, use `build.ps1` and `scripts/build_installer.ps1` with the .NET 8
SDK. Verify the installer payload, bundled CLI/runtime, upgrade preservation of settings/session,
and that the installed executable matches the tested build. Stop an idle runner gracefully before
upgrading. Do not run `scripts/test_installer.ps1` on a machine with an existing registered install;
the script requires a clean environment and exercises uninstall registration.

Publish only when requested. Release `Silentanator-Setup.exe` together with `SHA256SUMS.txt` so the
README's latest-download link continues to work. Verify the remote source/tag and uploaded asset
size and digest, and account for the tag-triggered release workflow before replacing assets.
