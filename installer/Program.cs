using System.Diagnostics;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Win32;

namespace SilentanatorInstaller;

internal static class Program
{
    internal const string ProductId = "f9334ef5-a351-4fba-a0a0-b563af7c6697";
    internal const string UninstallKey = @"Software\Microsoft\Windows\CurrentVersion\Uninstall\Silentanator";
    internal static readonly string DefaultDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "Programs", "Silentanator");
    internal static string Version => Assembly.GetExecutingAssembly().GetName().Version!.ToString(3);
    internal record Payload(string Sha256, int Files);

    [STAThread]
    static int Main(string[] args)
    {
        try
        {
            if (args.Contains("--validate-payload"))
            {
                var info = ValidatePayload();
                if (Option(args, "--report") is string report)
                    File.WriteAllText(report, JsonSerializer.Serialize(new { ok = true, files = info.Files, sha256 = info.Sha256 }));
                return 0;
            }
            if (args.Contains("--quiet"))
            {
                Install(Option(args, "--dir") ?? DefaultDirectory, !args.Contains("--no-shortcuts"), _ => { });
                return 0;
            }
            ApplicationConfiguration.Initialize();
            Application.Run(new InstallerForm());
            return 0;
        }
        catch (Exception exception)
        {
            if (Option(args, "--log") is string log) File.WriteAllText(log, exception.ToString());
            if (!args.Contains("--quiet") && !args.Contains("--validate-payload"))
                MessageBox.Show(exception.Message, "Silentanator installation", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
    }

    static string? Option(string[] args, string key)
    {
        var index = Array.IndexOf(args, key);
        return index >= 0 && index + 1 < args.Length ? args[index + 1] : null;
    }

    static Stream Resource(string name) => Assembly.GetExecutingAssembly().GetManifestResourceStream("Silentanator." + name)
        ?? throw new InvalidOperationException("The installer payload is missing.");

    static Payload ValidatePayload()
    {
        using var metadata = Resource("Payload.json");
        var info = JsonSerializer.Deserialize<Payload>(metadata) ?? throw new InvalidDataException("Invalid payload metadata.");
        using var stream = Resource("Payload.zip");
        var actual = Convert.ToHexString(SHA256.HashData(stream));
        if (!actual.Equals(info.Sha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("Installer checksum verification failed. Download the installer again.");
        stream.Position = 0;
        using var archive = new ZipArchive(stream, ZipArchiveMode.Read);
        foreach (var required in new[] { "Silentanator.exe", "SilentanatorSetup.exe", "vendor/codex/codex.exe" })
            if (!archive.Entries.Any(entry => entry.FullName.Replace('\\', '/') == required))
                throw new InvalidDataException("Installer is incomplete: " + required);
        if (archive.Entries.Count != info.Files) throw new InvalidDataException("Invalid payload file count.");
        return info;
    }

    internal static void Install(string directory, bool shortcuts, Action<string> status)
    {
        using var installing = new Mutex(false, @"Local\SilentanatorInstaller", out bool unique);
        if (!unique) throw new InvalidOperationException("Another Silentanator installer is already running.");
        if (Mutex.TryOpenExisting(@"Local\SilentanatorRunner", out var running))
        {
            running.Dispose();
            throw new InvalidOperationException("Close Silentanator with Ctrl+Alt+Q or Task Manager, then install again.");
        }
        directory = Path.GetFullPath(directory).TrimEnd(Path.DirectorySeparatorChar);
        if (directory.Equals(Path.GetPathRoot(directory)?.TrimEnd('\\'), StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("Choose an application folder, not a drive root.");
        var marker = Path.Combine(directory, ".silentanator-install");
        if (Directory.Exists(directory) && (!File.Exists(marker) || File.ReadAllText(marker).Trim() != ProductId))
            throw new InvalidOperationException("The destination already exists and is not a Silentanator installation.");
        status("Verifying the application package…");
        ValidatePayload();
        string parent = Path.GetDirectoryName(directory)!;
        Directory.CreateDirectory(parent);
        string staging = Path.Combine(parent, ".Silentanator-install-" + Guid.NewGuid().ToString("N"));
        string backup = staging + ".previous";
        Directory.CreateDirectory(staging);
        bool swapped = false;
        try
        {
            status("Installing the app, Python runtime, and Codex CLI…");
            var installedFiles = new List<string>();
            using (var stream = Resource("Payload.zip"))
            using (var archive = new ZipArchive(stream, ZipArchiveMode.Read))
            {
                foreach (var entry in archive.Entries)
                {
                    string target = Path.GetFullPath(Path.Combine(staging, entry.FullName));
                    if (!target.StartsWith(staging + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                        throw new InvalidDataException("Unsafe path in installer package.");
                    if (entry.Name.Length == 0) { Directory.CreateDirectory(target); continue; }
                    Directory.CreateDirectory(Path.GetDirectoryName(target)!);
                    entry.ExtractToFile(target);
                    installedFiles.Add(entry.FullName.Replace('\\', '/'));
                }
            }
            File.WriteAllText(Path.Combine(staging, ".silentanator-install"), ProductId);
            installedFiles.Add(".silentanator-install");
            installedFiles.Add(".silentanator-files.txt");
            File.WriteAllLines(Path.Combine(staging, ".silentanator-files.txt"), installedFiles);
            if (Directory.Exists(directory))
            {
                var previousManifest = Path.Combine(directory, ".silentanator-files.txt");
                var known = File.Exists(previousManifest)
                    ? new HashSet<string>(File.ReadAllLines(previousManifest), StringComparer.OrdinalIgnoreCase)
                    : new HashSet<string>(StringComparer.OrdinalIgnoreCase);
                var options = new EnumerationOptions { RecurseSubdirectories = true, AttributesToSkip = FileAttributes.ReparsePoint };
                foreach (var source in Directory.EnumerateFiles(directory, "*", options))
                {
                    var relative = Path.GetRelativePath(directory, source).Replace('\\', '/');
                    var destination = Path.Combine(staging, relative);
                    if (known.Contains(relative) || File.Exists(destination)) continue;
                    Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
                    File.Copy(source, destination);
                }
            }
            if (Directory.Exists(directory)) Directory.Move(directory, backup);
            Directory.Move(staging, directory);
            swapped = true;
            status("Registering shortcuts and the uninstaller…");
            if (shortcuts) CreateShortcuts(directory);
            using var key = Registry.CurrentUser.CreateSubKey(UninstallKey);
            key.SetValue("DisplayName", "Silentanator");
            key.SetValue("DisplayVersion", Version);
            key.SetValue("Publisher", "Hola3Dprint");
            key.SetValue("InstallLocation", directory);
            key.SetValue("DisplayIcon", Path.Combine(directory, "SilentanatorSetup.exe"));
            string command = $"\"{Path.Combine(directory, "Uninstall.exe")}\"";
            key.SetValue("UninstallString", command);
            key.SetValue("QuietUninstallString", command + " --quiet");
            key.SetValue("NoModify", 1, RegistryValueKind.DWord);
            key.SetValue("NoRepair", 1, RegistryValueKind.DWord);
            long size = Directory.EnumerateFiles(directory, "*", SearchOption.AllDirectories).Sum(path => new FileInfo(path).Length) / 1024;
            key.SetValue("EstimatedSize", (int)Math.Min(size, int.MaxValue), RegistryValueKind.DWord);
            if (Directory.Exists(backup)) Directory.Delete(backup, true);
            status("Installed. Open Setup to sign in with your ChatGPT account.");
        }
        catch
        {
            // Only delete directories created by this installation operation.
            if (swapped && Directory.Exists(directory) && File.ReadAllText(marker).Trim() == ProductId)
                Directory.Delete(directory, true);
            if (Directory.Exists(backup)) Directory.Move(backup, directory);
            throw;
        }
        finally
        {
            if (Directory.Exists(staging)) Directory.Delete(staging, true);
        }
    }

    static void CreateShortcuts(string directory)
    {
        Type type = Type.GetTypeFromProgID("WScript.Shell") ?? throw new InvalidOperationException("Windows shortcuts are unavailable.");
        dynamic shell = Activator.CreateInstance(type)!;
        string menu = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Programs), "Silentanator");
        Directory.CreateDirectory(menu);
        foreach (var (name, executable) in new[] { ("Silentanator Setup", "SilentanatorSetup.exe"), ("Run Silentanator", "Silentanator.exe") })
        {
            dynamic shortcut = shell.CreateShortcut(Path.Combine(menu, name + ".lnk"));
            shortcut.TargetPath = Path.Combine(directory, executable);
            shortcut.WorkingDirectory = directory;
            shortcut.Save();
        }
        dynamic desktop = shell.CreateShortcut(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.DesktopDirectory), "Silentanator Setup.lnk"));
        desktop.TargetPath = Path.Combine(directory, "SilentanatorSetup.exe");
        desktop.WorkingDirectory = directory;
        desktop.Save();
    }
}

internal sealed class InstallerForm : Form
{
    readonly Label status = new() { AutoSize = false, Height = 80, Dock = DockStyle.Fill, Text = "Install for your Windows account. No administrator access or separate Python installation is needed.\n\nAfter installation, sign in using your own ChatGPT account in Setup." };
    readonly Button install = new() { Text = "Install", AutoSize = true };
    readonly CheckBox launch = new() { Text = "Open Setup when installation finishes", Checked = true, AutoSize = true };
    readonly ProgressBar progress = new() { Dock = DockStyle.Fill, Height = 22 };
    bool finished;
    bool busy;

    internal InstallerForm()
    {
        Text = "Install Silentanator";
        Font = new Font("Segoe UI", 10);
        ClientSize = new Size(600, 330);
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        StartPosition = FormStartPosition.CenterScreen;
        var layout = new TableLayoutPanel { Dock = DockStyle.Fill, Padding = new Padding(24), RowCount = 5, ColumnCount = 1 };
        layout.Controls.Add(new Label { Text = "Silentanator", Font = new Font(Font.FontFamily, 23, FontStyle.Bold), AutoSize = true }, 0, 0);
        layout.Controls.Add(status, 0, 1);
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 55));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 30));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 35));
        layout.RowStyles.Add(new RowStyle(SizeType.Absolute, 38));
        layout.Controls.Add(progress, 0, 2);
        layout.Controls.Add(launch, 0, 3);
        layout.Controls.Add(install, 0, 4);
        Controls.Add(layout);
        install.Click += async (_, _) =>
        {
            if (finished) { Close(); return; }
            busy = true;
            install.Enabled = false;
            launch.Enabled = false;
            progress.Style = ProgressBarStyle.Marquee;
            try
            {
                var updates = new Progress<string>(message => status.Text = message);
                await Task.Run(() => Program.Install(Program.DefaultDirectory, true, message => ((IProgress<string>)updates).Report(message)));
                finished = true;
                install.Text = "Finish";
                if (launch.Checked) Process.Start(new ProcessStartInfo(Path.Combine(Program.DefaultDirectory, "SilentanatorSetup.exe")) { UseShellExecute = true });
            }
            catch (Exception exception) { status.Text = exception.Message; }
            finally { busy = false; install.Enabled = true; launch.Enabled = true; progress.Style = ProgressBarStyle.Blocks; }
        };
        FormClosing += (_, args) => { if (busy) args.Cancel = true; };
    }
}
