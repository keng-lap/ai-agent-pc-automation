using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Security.Principal;
using System.Text;
using InstallerHelper.Security;

if (!OperatingSystem.IsWindows())
    throw new PlatformNotSupportedException("These integration checks require Windows.");

RunTokenChecks();
RunAuthenticodeChecks();
RunJobObjectChecks();
Console.WriteLine("Windows Installer Helper security integration checks passed.");

static void RunTokenChecks()
{
    using var identity = WindowsIdentity.GetCurrent();
    var sid = identity.User?.Value ?? throw new InvalidOperationException("Current Windows SID is unavailable.");

    if (GetTokenElevation())
    {
        WindowsSecurity.RequireElevatedTokenForSid(sid);
        ExpectUnauthorized(() => WindowsSecurity.RequireElevatedTokenForSid("S-1-5-21-0-0-0-9999"));
        Console.WriteLine("PASS: elevated token accepts the actual SID and rejects a mismatched SID.");
    }
    else
    {
        ExpectUnauthorized(() => WindowsSecurity.RequireElevatedTokenForSid(sid));
        Console.WriteLine("PASS: non-elevated token rejected (SID mismatch check requires an elevated runner).");
    }
}

static void ExpectUnauthorized(Action action)
{
    try
    {
        action();
    }
    catch (UnauthorizedAccessException)
    {
        return;
    }
    throw new InvalidOperationException("A forbidden token/SID was incorrectly accepted.");
}

static void ExpectCryptographicFailure(Action action)
{
    try
    {
        action();
    }
    catch (CryptographicException)
    {
        return;
    }
    throw new InvalidOperationException("An invalid Authenticode signature or certificate pin was incorrectly accepted.");
}

static bool GetTokenElevation()
{
    if (!Native.OpenProcessToken(Native.GetCurrentProcess(), 0x0008, out var token))
        throw new Win32Exception(Marshal.GetLastWin32Error());
    using (token)
    {
        var size = Marshal.SizeOf<TokenElevation>();
        if (!Native.GetTokenInformation(token, 20, out var elevation, size, out var returned)
            || returned < size)
            throw new Win32Exception(Marshal.GetLastWin32Error());
        return elevation.TokenIsElevated != 0;
    }
}

static void RunAuthenticodeChecks()
{
    var tempDirectory = Path.Combine(Path.GetTempPath(), "installer-helper-security-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempDirectory);
    var signedFile = Path.Combine(tempDirectory, "signed-test.ps1");
    var thumbprintFile = Path.Combine(tempDirectory, "thumbprint.txt");
    string? thumbprint = null;

    try
    {
        var setupScript = $@"
$ErrorActionPreference = 'Stop'
$cert = New-SelfSignedCertificate -Subject 'CN=InstallerHelper Integration Test' -Type CodeSigningCert -CertStoreLocation 'Cert:\CurrentUser\My' -HashAlgorithm SHA256
$root = Get-Item 'Cert:\CurrentUser\Root'
$root.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
$root.Add($cert)
$root.Close()
$publishers = Get-Item 'Cert:\CurrentUser\TrustedPublisher'
$publishers.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
$publishers.Add($cert)
$publishers.Close()
Set-Content -LiteralPath '{EscapePowerShell(signedFile)}' -Value 'Write-Output ""signed integration test""' -Encoding UTF8
Set-AuthenticodeSignature -LiteralPath '{EscapePowerShell(signedFile)}' -Certificate $cert -HashAlgorithm SHA256 | Out-Null
Set-Content -LiteralPath '{EscapePowerShell(thumbprintFile)}' -Value $cert.Thumbprint -NoNewline
";
        RunPowerShell(setupScript);
        thumbprint = File.ReadAllText(thumbprintFile).Trim();
        if (thumbprint.Length == 0)
            throw new InvalidOperationException("PowerShell did not return the test certificate thumbprint.");

        using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
        store.Open(OpenFlags.ReadOnly);
        var matches = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, false);
        if (matches.Count != 1)
            throw new InvalidOperationException("The temporary code-signing certificate was not found.");
        using var certificate = new X509Certificate2(matches[0]);
        var pin = Convert.ToHexString(SHA256.HashData(certificate.RawData));

        WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, pin);
        Console.WriteLine("PASS: trusted Authenticode signature with the pinned SHA-256 certificate accepted.");

        ExpectCryptographicFailure(() => WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, new string('0', 64)));
        Console.WriteLine("PASS: valid signature from an unpinned certificate rejected.");

        File.AppendAllText(signedFile, Environment.NewLine + "# tampered after signing");
        ExpectCryptographicFailure(() => WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, pin));
        Console.WriteLine("PASS: modified signed file rejected.");
    }
    finally
    {
        if (thumbprint is not null)
        {
            var cleanup = $@"
$ErrorActionPreference = 'Stop'
$thumb = '{EscapePowerShell(thumbprint)}'
foreach ($location in @('My', 'Root', 'TrustedPublisher')) {{
  $store = Get-Item ('Cert:\CurrentUser\' + $location)
  $store.Open([System.Security.Cryptography.X509Certificates.OpenFlags]::ReadWrite)
  foreach ($cert in @($store.Certificates | Where-Object Thumbprint -eq $thumb)) {{ $store.Remove($cert) }}
  $store.Close()
}}
";
            RunPowerShell(cleanup);
        }
        Directory.Delete(tempDirectory, recursive: true);
    }
}

static string EscapePowerShell(string value) => value.Replace("'", "''", StringComparison.Ordinal);

static void RunPowerShell(string script)
{
    var encoded = Convert.ToBase64String(Encoding.Unicode.GetBytes(script));
    using var process = Process.Start(new ProcessStartInfo
    {
        FileName = "powershell.exe",
        Arguments = "-NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + encoded,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true
    }) ?? throw new InvalidOperationException("Could not start Windows PowerShell for Authenticode integration checks.");

    var stdout = process.StandardOutput.ReadToEnd();
    var stderr = process.StandardError.ReadToEnd();
    process.WaitForExit();
    if (process.ExitCode != 0)
        throw new InvalidOperationException("PowerShell Authenticode setup/cleanup failed: " + stderr + stdout);
}

static void RunJobObjectChecks()
{
    using var job = new WindowsJobObject();
    var process = SuspendedChild.Start();
    try
    {
        job.AssignSuspendedProcess(process.ProcessHandle);
        if (Native.ResumeThread(process.ThreadHandle) == uint.MaxValue)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not resume the contained test process.");

        job.Terminate();
        job.WaitForEmpty(TimeSpan.FromSeconds(10));
        Console.WriteLine("PASS: process assigned while suspended; Job Object terminated its process tree.");
    }
    finally
    {
        _ = Native.TerminateProcess(process.ProcessHandle, 1);
        _ = Native.CloseHandle(process.ThreadHandle);
        _ = Native.CloseHandle(process.ProcessHandle);
    }
}

static class SuspendedChild
{
    internal static ProcessHandles Start()
    {
        var system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        var executable = Path.Combine(system, "cmd.exe");
        var command = new StringBuilder($"\\\"{executable}\\\" /c ping -n 30 127.0.0.1 > nul");
        var startup = new StartupInfo { Cb = Marshal.SizeOf<StartupInfo>() };
        if (!Native.CreateProcess(
                executable, command, IntPtr.Zero, IntPtr.Zero,
                false, 0x00000004 | 0x08000000, IntPtr.Zero, system,
                ref startup, out var info))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not create suspended test process.");
        return new ProcessHandles(info.Process, info.Thread);
    }
}

readonly record struct ProcessHandles(IntPtr ProcessHandle, IntPtr ThreadHandle);

[StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
struct StartupInfo
{
    public int Cb;
    public string? Reserved;
    public string? Desktop;
    public string? Title;
    public int X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
    public short ShowWindow, Reserved2;
    public IntPtr Reserved2Pointer, StdInput, StdOutput, StdError;
}

[StructLayout(LayoutKind.Sequential)]
struct ProcessInformation
{
    public IntPtr Process;
    public IntPtr Thread;
    public uint ProcessId;
    public uint ThreadId;
}

[StructLayout(LayoutKind.Sequential)]
struct TokenElevation
{
    public uint TokenIsElevated;
}

static class Native
{
    [DllImport("kernel32.dll")]
    internal static extern IntPtr GetCurrentProcess();

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool OpenProcessToken(IntPtr process, uint access, out Microsoft.Win32.SafeHandles.SafeAccessTokenHandle token);

    [DllImport("advapi32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool GetTokenInformation(Microsoft.Win32.SafeHandles.SafeAccessTokenHandle token, int infoClass, out TokenElevation info, int size, out int returned);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true, EntryPoint = "CreateProcessW")]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CreateProcess(string application, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes, bool inheritHandles, uint flags, IntPtr environment, string currentDirectory, ref StartupInfo startup, out ProcessInformation processInfo);

    [DllImport("kernel32.dll", SetLastError = true)]
    internal static extern uint ResumeThread(IntPtr thread);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(IntPtr process, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(IntPtr handle);
}
