# Third-party components

The Windows distribution includes Python and the dependencies listed in `requirements.lock`. Their license texts are copied into the installed `licenses` directory during the build.

The official OpenAI Codex CLI, version `rust-v0.166.0`, is redistributed under Apache-2.0. Its LICENSE and NOTICE are included under `vendor/codex`. The official executable is unmodified; its filename and package entrypoint metadata are adjusted for the app layout. Download URLs and required SHA256 values are recorded in `scripts/fetch_codex.ps1`.

The installer includes Microsoft's .NET 8 Windows runtime. .NET runtime components are distributed under the MIT license and their applicable third-party licenses. See the [.NET runtime license](https://github.com/dotnet/runtime/blob/main/LICENSE.TXT), [runtime third-party notices](https://github.com/dotnet/runtime/blob/main/THIRD-PARTY-NOTICES.TXT), and [Windows Forms license](https://github.com/dotnet/winforms/blob/main/LICENSE.TXT).

Silentanator is not affiliated with OpenAI, Microsoft, GitHub, or Instructure. Users sign in with their own account; authentication credentials are not redistributed.
