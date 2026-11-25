using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;
using InstallerHelper.Security;

if (!OperatingSystem.IsWindows())
    throw new PlatformNotSupportedException("These integration checks require Windows.");

RunTokenChecks();
RunJobObjectChecks();
Console.WriteLine("Windows Installer Helper security integration checks passed.");

static void RunTokenChecks()
{
    using var identity = WindowsIdentity.GetCurrent();
    var sid = identity.User?.Value ?? throw new InvalidOperationException("Current Windows SID is unavailable.");

    if (GetTokenElevation())
    {
        WindowsSecurity.RequireElevatedTokenForSid(sid);
        Console.WriteLine("PASS: elevated token and matching SID accepted.");
    }
    else
    {
        ExpectUnauthorized(() => WindowsSecurity.RequireElevatedTokenForSid(sid));
        Console.WriteLine("PASS: non-elevated token rejected.");
    }

    ExpectUnauthorized(() => WindowsSecurity.RequireElevatedTokenForSid("S-1-5-21-0-0-0-9999"));
    Console.WriteLine("PASS: mismatched/non-elevated identity rejected.");
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
        var command = new StringBuilder($"\"{executable}\" /c ping -n 30 127.0.0.1 > nul");
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
