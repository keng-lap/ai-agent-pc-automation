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
RunApprovalTicketChecks();
RunDurableNonceStoreChecks();
RunDpapiApprovalKeyChecks();
ProtectedApprovalKeyStoreChecks.Run();
RunAuthenticodeChecks();
RunJobObjectChecks();
Console.WriteLine("Windows Installer Helper security integration checks passed.");


static void RunApprovalTicketChecks()
{
    var now = DateTimeOffset.UtcNow;
    var digest = new string('A', 64);
    var key = RandomNumberGenerator.GetBytes(32);
    var unsigned = new InstallerApprovalTicket(
        ProtocolVersion: InstallerApprovalTicket.CurrentProtocolVersion,
        TicketId: Guid.NewGuid().ToString("N"),
        RequesterSid: "S-1-5-21-100-200-300-1001",
        PlanId: new string('b', 32),
        ApprovalDigest: digest,
        PackageId: "Example.Package",
        Version: "1.2.3",
        Architecture: "x64",
        Scope: "machine",
        InstallerSha256: new string('c', 64),
        Nonce: Convert.ToHexString(RandomNumberGenerator.GetBytes(32)),
        IssuedAtUnixSeconds: now.ToUnixTimeSeconds(),
        ExpiresAtUnixSeconds: now.AddSeconds(60).ToUnixTimeSeconds(),
        SignatureSha256: string.Empty);

    var signed = unsigned.Sign(key);
    signed.Verify(key, unsigned.RequesterSid, digest, now);
    Console.WriteLine("PASS: exact-action machine-scope approval ticket HMAC accepted.");

    ExpectTicketFailure(() => signed.Verify(key, "S-1-5-21-100-200-300-9999", digest, now));
    ExpectTicketFailure(() => signed.Verify(key, unsigned.RequesterSid, new string('D', 64), now));
    ExpectTicketFailure(() => (signed with { Version = "9.9.9" }).Verify(key, unsigned.RequesterSid, digest, now));
    ExpectTicketFailure(() => signed.Verify(key, unsigned.RequesterSid, digest, now.AddMinutes(3)));
    ExpectTicketFailure(() => signed.Verify(RandomNumberGenerator.GetBytes(32), unsigned.RequesterSid, digest, now));
    ExpectTicketFailure(() => (signed with { Scope = "user" }).Verify(key, unsigned.RequesterSid, digest, now));
    ExpectTicketFailure(() => (signed with { Version = null! }).Verify(key, unsigned.RequesterSid, digest, now));
    ExpectTicketFailure(() => (signed with { SignatureSha256 = null! }).Verify(key, unsigned.RequesterSid, digest, now));
    Console.WriteLine("PASS: approval ticket rejects wrong SID, action digest, package version, expiry, key, and scope.");
}

static void ExpectTicketFailure(Action action)
{
    try
    {
        action();
    }
    catch (CryptographicException)
    {
        return;
    }
    throw new InvalidOperationException("An invalid approval ticket was incorrectly accepted.");
}

static void RunDurableNonceStoreChecks()
{
    var directory = Path.Combine(Path.GetTempPath(), "installer-helper-nonces-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(directory);
    try
    {
        var nonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var ticketId = Guid.NewGuid().ToString("N");
        var expires = DateTimeOffset.UtcNow.AddMinutes(2);
        var now = DateTimeOffset.UtcNow;
        var store = new DurableNonceStore(directory);
        store.Consume(nonce, ticketId, expires, now);
        ExpectTicketFailure(() => store.Consume(nonce, ticketId, expires, now));

        // A new instance models a Helper/backend process restart.
        var restartedStore = new DurableNonceStore(directory);
        ExpectTicketFailure(() => restartedStore.Consume(nonce, ticketId, expires, now));

        var concurrentNonce = Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
        var successes = 0;
        Parallel.For(0, 16, _ =>
        {
            try
            {
                new DurableNonceStore(directory).Consume(concurrentNonce, ticketId, expires, now);
                Interlocked.Increment(ref successes);
            }
            catch (CryptographicException)
            {
                // Expected for every contender except the single atomic winner.
            }
        });
        if (successes != 1)
            throw new InvalidOperationException($"Expected exactly one nonce consumer; observed {successes}.");
        ExpectTicketFailure(() => store.Consume(
            Convert.ToHexString(RandomNumberGenerator.GetBytes(32)),
            ticketId,
            now.AddSeconds(-1),
            now));
        Console.WriteLine("PASS: durable nonce is single-use across instances/restarts and concurrent consumers.");
    }
    finally
    {
        Directory.Delete(directory, recursive: true);
    }
}

static void RunDpapiApprovalKeyChecks()
{
    var key = RandomNumberGenerator.GetBytes(32);
    var protectedKey = DpapiApprovalKeyProtector.Protect(key);
    var recovered = DpapiApprovalKeyProtector.Unprotect(protectedKey);
    if (!CryptographicOperations.FixedTimeEquals(key, recovered))
        throw new InvalidOperationException("DPAPI did not recover the original approval key.");
    Console.WriteLine("PASS: machine-scope DPAPI protects and recovers the approval HMAC key.");

    var tampered = protectedKey.ToArray();
    tampered[^1] ^= 0x01;
    ExpectTicketFailure(() => DpapiApprovalKeyProtector.Unprotect(tampered));
    ExpectTicketFailure(() => DpapiApprovalKeyProtector.Protect(new byte[16]));
    Console.WriteLine("PASS: DPAPI rejects a modified protected key and undersized HMAC keys.");

    CryptographicOperations.ZeroMemory(key);
    CryptographicOperations.ZeroMemory(recovered);
    CryptographicOperations.ZeroMemory(protectedKey);
    CryptographicOperations.ZeroMemory(tampered);
}

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
    if (!GetTokenElevation())
        throw new UnauthorizedAccessException("Authenticode integration checks require an elevated Windows runner to write LocalMachine trust stores.");

    var tempDirectory = Path.Combine(Path.GetTempPath(), "installer-helper-authenticode-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(tempDirectory);
    var signedFile = Path.Combine(tempDirectory, "signed-test.dll");
    var pfxFile = Path.Combine(tempDirectory, "test-signing.pfx");
    var password = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32));
    X509Certificate2? certificateWithKey = null;
    string? thumbprint = null;

    try
    {
        Console.WriteLine("Authenticode: [1/10] copying test binary.");
        var currentAssembly = typeof(Program).Assembly.Location;
        File.Copy(currentAssembly, signedFile, overwrite: true);
        Console.WriteLine("Authenticode: [1/10] test binary copied.");

        Console.WriteLine("Authenticode: [2/10] creating RSA key.");
        using var rsa = RSA.Create(2048);
        Console.WriteLine("Authenticode: [2/10] RSA key created.");

        {
            Console.WriteLine("Authenticode: [3/10] constructing certificate request.");
            var request = new CertificateRequest(
                "CN=InstallerHelper Integration Test",
                rsa,
                HashAlgorithmName.SHA256,
                RSASignaturePadding.Pkcs1);
            request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, false));
            request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature, false));
            var eku = new OidCollection { new("1.3.6.1.5.5.7.3.3") };
            request.CertificateExtensions.Add(new X509EnhancedKeyUsageExtension(eku, false));
            Console.WriteLine("Authenticode: [3/10] certificate request ready.");
            Console.WriteLine("Authenticode: [4/10] creating self-signed certificate.");
            using var created = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-5), DateTimeOffset.UtcNow.AddDays(2));
            Console.WriteLine("Authenticode: [4/10] self-signed certificate created.");
            Console.WriteLine("Authenticode: [5/10] exporting and importing PFX.");
            var pfxBytes = created.Export(X509ContentType.Pfx, password);
            certificateWithKey = new X509Certificate2(
                pfxBytes,
                password,
                X509KeyStorageFlags.Exportable | X509KeyStorageFlags.EphemeralKeySet);
            Console.WriteLine("Authenticode: [5/10] PFX imported.");
        }

        thumbprint = certificateWithKey.Thumbprint;
        Console.WriteLine("Authenticode: [6/10] adding private certificate to CurrentUser\\My.");
        AddCertificateToStore(certificateWithKey, StoreName.My, StoreLocation.CurrentUser);
        Console.WriteLine("Authenticode: [6/10] certificate added to CurrentUser\\My.");

        // Follow the established PowerToys signing-test layout: keep the private key
        // in CurrentUser\\My, and trust only the public certificate in machine stores.
        Console.WriteLine("Authenticode: [7/10] adding public certificate to LocalMachine\\Root.");
        using (var rootCert = new X509Certificate2(certificateWithKey.RawData))
            AddCertificateToStore(rootCert, StoreName.Root, StoreLocation.LocalMachine);
        Console.WriteLine("Authenticode: [7/10] certificate added to LocalMachine\\Root.");

        Console.WriteLine("Authenticode: [8/10] adding public certificate to LocalMachine\\TrustedPeople.");
        using (var trustedPeopleCert = new X509Certificate2(certificateWithKey.RawData))
            AddCertificateToStore(trustedPeopleCert, StoreName.TrustedPeople, StoreLocation.LocalMachine);
        Console.WriteLine("Authenticode: [8/10] certificate added to LocalMachine\\TrustedPeople.");

        using (var currentUserTrustedPeopleCert = new X509Certificate2(certificateWithKey.RawData))
            AddCertificateToStore(currentUserTrustedPeopleCert, StoreName.TrustedPeople, StoreLocation.CurrentUser);

        Console.WriteLine("Authenticode: [9/10] exporting PFX file.");
        File.WriteAllBytes(pfxFile, certificateWithKey.Export(X509ContentType.Pfx, password));
        Console.WriteLine("Authenticode: [9/10] PFX file written.");
        Console.WriteLine("Authenticode: [10/10] locating Windows SDK SignTool.");
        var signTool = FindSignTool();
        Console.WriteLine("Authenticode: signing test binary.");
        RunProcess(signTool, new[]
        {
            "sign", "/f", pfxFile, "/p", password, "/fd", "SHA256", signedFile
        });

        var pin = Convert.ToHexString(SHA256.HashData(certificateWithKey.RawData));
        Console.WriteLine("Authenticode: verifying valid signature.");
        WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, pin);
        Console.WriteLine("PASS: trusted Authenticode signature with the pinned SHA-256 certificate accepted.");

        Console.WriteLine("Authenticode: checking wrong certificate pin rejection.");
        ExpectCryptographicFailure(() => WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, new string('0', 64)));
        Console.WriteLine("PASS: valid signature from an unpinned certificate rejected.");

        File.AppendAllText(signedFile, "tampered");
        Console.WriteLine("Authenticode: checking modified binary rejection.");
        ExpectCryptographicFailure(() => WindowsSecurity.RequireTrustedAuthenticodeSignature(signedFile, pin));
        Console.WriteLine("PASS: modified signed file rejected.");
    }
    finally
    {
        certificateWithKey?.Dispose();
        if (thumbprint is not null)
        {
            RemoveCertificateFromStore(thumbprint, StoreName.My, StoreLocation.CurrentUser);
            RemoveCertificateFromStore(thumbprint, StoreName.Root, StoreLocation.LocalMachine);
            RemoveCertificateFromStore(thumbprint, StoreName.TrustedPeople, StoreLocation.LocalMachine);
            RemoveCertificateFromStore(thumbprint, StoreName.TrustedPeople, StoreLocation.CurrentUser);
        }

        if (Directory.Exists(tempDirectory))
            Directory.Delete(tempDirectory, recursive: true);
    }
}

static void AddCertificateToStore(X509Certificate2 certificate, StoreName storeName, StoreLocation storeLocation)
{
    Console.WriteLine($"Authenticode: opening {storeLocation}\\{storeName} store.");
    using var store = new X509Store(storeName, storeLocation);
    store.Open(OpenFlags.ReadWrite);
    Console.WriteLine($"Authenticode: opened {storeLocation}\\{storeName} store; adding certificate.");
    store.Add(certificate);
    Console.WriteLine($"Authenticode: added certificate to {storeLocation}\\{storeName} store.");
}

static void RemoveCertificateFromStore(string thumbprint, StoreName storeName, StoreLocation storeLocation)
{
    using var store = new X509Store(storeName, storeLocation);
    store.Open(OpenFlags.ReadWrite);
    var matches = store.Certificates.Find(X509FindType.FindByThumbprint, thumbprint, false);
    foreach (var certificate in matches)
        store.Remove(certificate);
}

static string FindSignTool()
{
    var kitsRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.ProgramFilesX86),
        "Windows Kits", "10", "bin");
    if (Directory.Exists(kitsRoot))
    {
        foreach (var versionDirectory in Directory.GetDirectories(kitsRoot).OrderByDescending(path => path, StringComparer.OrdinalIgnoreCase))
        {
            var candidate = Path.Combine(versionDirectory, "x64", "signtool.exe");
            if (File.Exists(candidate))
                return candidate;
        }
    }

    throw new FileNotFoundException("Windows SDK SignTool was not found; Authenticode integration checks cannot run.");
}

static void RunProcess(string executable, IEnumerable<string> arguments)
{
    var startInfo = new ProcessStartInfo
    {
        FileName = executable,
        UseShellExecute = false,
        RedirectStandardOutput = true,
        RedirectStandardError = true,
        CreateNoWindow = true
    };
    foreach (var argument in arguments)
        startInfo.ArgumentList.Add(argument);

    using var process = Process.Start(startInfo)
        ?? throw new InvalidOperationException("Could not start Windows SDK SignTool.");
    var stdoutTask = process.StandardOutput.ReadToEndAsync();
    var stderrTask = process.StandardError.ReadToEndAsync();
    if (!process.WaitForExit(90_000))
    {
        process.Kill(entireProcessTree: true);
        throw new TimeoutException("SignTool exceeded the 90-second integration-test limit: " + executable);
    }
    Task.WaitAll(stdoutTask, stderrTask);
    if (process.ExitCode != 0)
        throw new InvalidOperationException($"SignTool failed with exit code {process.ExitCode}: {stderrTask.Result}{stdoutTask.Result}");
}

static void RunJobObjectChecks()
{
    using (var job = new WindowsJobObject())
    {
        var process = SuspendedChild.Start();
        try
        {
            job.AssignSuspendedProcess(process.ProcessHandle);
            if (Native.ResumeThread(process.ThreadHandle) == uint.MaxValue)
                throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not resume the contained test process.");

            WaitForContainedChild(job);

            job.Terminate();
            job.WaitForEmpty(TimeSpan.FromSeconds(10));
            Console.WriteLine("PASS: suspended root assigned before resume; child process joined the same Job Object; explicit tree termination reached zero active processes.");
        }
        finally
        {
            _ = Native.TerminateProcess(process.ProcessHandle, 1);
            _ = Native.CloseHandle(process.ThreadHandle);
            _ = Native.CloseHandle(process.ProcessHandle);
        }
    }

    var killOnCloseJob = new WindowsJobObject();
    var killOnCloseProcess = SuspendedChild.Start();
    try
    {
        killOnCloseJob.AssignSuspendedProcess(killOnCloseProcess.ProcessHandle);
        if (Native.ResumeThread(killOnCloseProcess.ThreadHandle) == uint.MaxValue)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not resume the kill-on-close test process.");

        WaitForContainedChild(killOnCloseJob);
        killOnCloseJob.Dispose();
        if (Native.WaitForSingleObject(killOnCloseProcess.ProcessHandle, 10_000) != 0)
            throw new InvalidOperationException("Closing the Job Object did not terminate its root process.");
        Console.WriteLine("PASS: closing the Helper-owned Job Object terminated the root process and its contained child.");
    }
    finally
    {
        killOnCloseJob.Dispose();
        _ = Native.TerminateProcess(killOnCloseProcess.ProcessHandle, 1);
        _ = Native.CloseHandle(killOnCloseProcess.ThreadHandle);
        _ = Native.CloseHandle(killOnCloseProcess.ProcessHandle);
    }
}

static void WaitForContainedChild(WindowsJobObject job)
{
    var deadline = DateTime.UtcNow + TimeSpan.FromSeconds(5);
    uint activeProcesses;
    do
    {
        activeProcesses = job.GetActiveProcessCount();
        if (activeProcesses >= 2)
            return;
        Thread.Sleep(50);
    } while (DateTime.UtcNow < deadline);

    throw new InvalidOperationException("The child process was not observed inside the Job Object.");
}

static class SuspendedChild
{
    internal static ProcessHandles Start()
    {
        var system = Environment.GetFolderPath(Environment.SpecialFolder.System);
        var executable = Path.Combine(system, "cmd.exe");
        var command = new StringBuilder($"\\\"{executable}\\\" /c start \"\" /b ping -n 30 127.0.0.1 & ping -n 30 127.0.0.1");
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
    internal static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool TerminateProcess(IntPtr process, uint exitCode);

    [DllImport("kernel32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)]
    internal static extern bool CloseHandle(IntPtr handle);
}
