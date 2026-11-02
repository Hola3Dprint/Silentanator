---
name: silentanator-course-context
description: Maintain and validate course-document retrieval in Silentanator, including per-session selection, local indexing, cited solving, and packaged Windows verification. Use for this repository's course-context features rather than general document questions.
---

# Silentanator course context

## Architecture and constraints

- `silentanator/course_context.py` discovers direct course folders, extracts source-labelled text, caches by file metadata, and retrieves bounded excerpts. `core.solve` uses a screenshot-only Codex query to obtain search terms before the final solve. Preserve the no-tools prompt, read-only sandbox, ChatGPT sign-in path, and credential isolation.
- Store selection in `StudySession` state, not a global course setting. Changing course starts a fresh session while preserving earlier notes. Restore selection across restarts. Existing sessions without a course remain screenshot-only.
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

For an authorized Windows release, use `build.ps1` and `scripts/build_installer.ps1` with the .NET 8
SDK. Verify the installer payload, bundled CLI/runtime, upgrade preservation of settings/session,
and that the installed executable matches the tested build. Stop an idle runner gracefully before
upgrading. Do not run `scripts/test_installer.ps1` on a machine with an existing registered install;
the script requires a clean environment and exercises uninstall registration.

Publish only when requested. Release `Silentanator-Setup.exe` together with `SHA256SUMS.txt` so the
README's latest-download link continues to work. Verify the remote source/tag and uploaded asset
size and digest, and account for the tag-triggered release workflow before replacing assets.
