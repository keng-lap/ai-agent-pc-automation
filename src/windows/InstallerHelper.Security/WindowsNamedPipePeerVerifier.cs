using System.ComponentModel;
using System.IO.Pipes;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

namespace InstallerHelper.Security;

/// <summary>
/// Named-pipe identity checks. A pipe name is not an authorization boundary:
/// callers must create the pipe with BuildServerPipeSddl and verify the peer
/// process token after connection.
/// </summary>
public static class WindowsNamedPipePeerVerifier
{
    private const uint ProcessQueryLimitedInformation = 0x1000;
    private const uint TokenQuery = 0x0008;
    private const int TokenUserClass = 1;
    private const int TokenStatisticsClass = 10;
    private const int TokenSessionIdClass = 12;
    private const int TokenElevationClass = 20;

    public static string CreatePipeName(string ticketId)
    {
        if (ticketId is null || ticketId.Length != 32 || ticketId.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Pipe ticket ID must be 32 hexadecimal characters.", nameof(ticketId));
        return "KengLap.InstallerHelper." + ticketId.ToUpperInvariant();
    }

    /// <summary>
    /// Returns a protected DACL for CreateNamedPipeW security attributes.
    /// The approving user's SID receives read/write; SYSTEM and Administrators
    /// receive full control. Remote clients must also be rejected at pipe creation.
    /// </summary>
    public static string BuildServerPipeSddl(string requesterSid)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows named-pipe security is Windows-only.");
        if (string.IsNullOrWhiteSpace(requesterSid))
            throw new ArgumentException("Requester SID is required.", nameof(requesterSid));

        var sid = new SecurityIdentifier(requesterSid);
        return $"D:P(A;;GA;;;SY)(A;;GA;;;BA)(A;;GRGW;;;{sid.Value})";
    }

    public static WindowsTokenIdentityInfo RequireClientIdentity(
        SafePipeHandle serverPipeHandle,
        string expectedRequesterSid,
        string expectedAuthenticationId,
        int expectedSessionId,
        bool requireNonElevatedClient = true)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows named-pipe peer verification is Windows-only.");
        if (serverPipeHandle is null || serverPipeHandle.IsInvalid || serverPipeHandle.IsClosed)
            throw new ArgumentException("A connected server pipe handle is required.", nameof(serverPipeHandle));
        if (!Native.GetNamedPipeClientProcessId(serverPipeHandle, out var processId) || processId == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not identify the named-pipe client process.");

        var identity = ReadProcessIdentity(processId);
        if (!StringComparer.Ordinal.Equals(identity.UserSid, expectedRequesterSid)
            || !StringComparer.Ordinal.Equals(identity.AuthenticationId, expectedAuthenticationId)
            || identity.SessionId != expectedSessionId
            || (requireNonElevatedClient && identity.IsElevated))
            throw new UnauthorizedAccessException("Named-pipe client process token does not match the approved non-elevated requester session.");

        return identity;
    }

    /// <summary>
    /// Verifies the connected pipe server is the pinned elevated Helper process.
    /// Call this on the unelevated client end before sending an approval ticket or nonce.
    /// </summary>
    public static WindowsTokenIdentityInfo RequireServerIdentity(
        SafePipeHandle clientPipeHandle,
        string expectedRequesterSid,
        string expectedAuthenticationId,
        int expectedSessionId,
        string expectedHelperImagePath,
        string expectedCertificateSha256)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows named-pipe peer verification is Windows-only.");
        if (clientPipeHandle is null || clientPipeHandle.IsInvalid || clientPipeHandle.IsClosed)
            throw new ArgumentException("A connected client pipe handle is required.", nameof(clientPipeHandle));
        if (string.IsNullOrWhiteSpace(expectedHelperImagePath) || string.IsNullOrWhiteSpace(expectedCertificateSha256))
            throw new ArgumentException("Pinned Helper path and certificate SHA-256 are required.");
        if (!Native.GetNamedPipeServerProcessId(clientPipeHandle, out var processId) || processId == 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not identify the named-pipe server process.");

        var identity = ReadProcessIdentity(processId);
        if (!StringComparer.Ordinal.Equals(identity.UserSid, expectedRequesterSid)
            || !StringComparer.Ordinal.Equals(identity.AuthenticationId, expectedAuthenticationId)
            || identity.SessionId != expectedSessionId
            || !identity.IsElevated)
            throw new UnauthorizedAccessException("Named-pipe server token does not match the expected elevated Helper identity.");

        using var process = Native.OpenProcess(ProcessQueryLimitedInformation, false, processId);
        if (process.IsInvalid)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the named-pipe server process.");
        var imagePath = QueryProcessImagePath(process);
        var expectedPath = Path.GetFullPath(expectedHelperImagePath);
        if (!StringComparer.OrdinalIgnoreCase.Equals(Path.GetFullPath(imagePath), expectedPath))
            throw new UnauthorizedAccessException("Named-pipe server executable path does not match the installed Helper path.");

        WindowsSecurity.RequireTrustedAuthenticodeSignature(imagePath, expectedCertificateSha256);
        return identity;
    }

    private static string QueryProcessImagePath(SafeProcessHandle process)
    {
        var capacity = 32768;
        var path = new StringBuilder(capacity);
        if (!Native.QueryFullProcessImageName(process, 0, path, ref capacity) || capacity <= 0)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query named-pipe server executable path.");
        return path.ToString();
    }

    private static WindowsTokenIdentityInfo ReadProcessIdentity(uint processId)
    {
        using var process = Native.OpenProcess(ProcessQueryLimitedInformation, false, processId);
        if (process.IsInvalid)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the named-pipe peer process.");
        if (!Native.OpenProcessToken(process, TokenQuery, out var token))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the named-pipe peer token.");
        using (token)
        {
            var userBuffer = QueryTokenBuffer(token, TokenUserClass);
            string sid;
            try
            {
                var user = Marshal.PtrToStructure<TokenUser>(userBuffer);
                sid = new SecurityIdentifier(user.UserSid).Value;
            }
            finally { Marshal.FreeHGlobal(userBuffer); }

            var sessionBuffer = Marshal.AllocHGlobal(sizeof(int));
            int sessionId;
            try
            {
                if (!Native.GetTokenInformation(token, TokenSessionIdClass, sessionBuffer, sizeof(int), out var returned)
                    || returned < sizeof(int))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query peer session ID.");
                sessionId = Marshal.ReadInt32(sessionBuffer);
            }
            finally { Marshal.FreeHGlobal(sessionBuffer); }

            var statsBuffer = QueryTokenBuffer(token, TokenStatisticsClass);
            string authenticationId;
            try
            {
                var stats = Marshal.PtrToStructure<TokenStatistics>(statsBuffer);
                var luid = ((ulong)(uint)stats.AuthenticationId.HighPart << 32) | stats.AuthenticationId.LowPart;
                authenticationId = luid.ToString("X16", System.Globalization.CultureInfo.InvariantCulture);
            }
            finally { Marshal.FreeHGlobal(statsBuffer); }

            var elevationBuffer = Marshal.AllocHGlobal(sizeof(uint));
            bool elevated;
            try
            {
                if (!Native.GetTokenInformation(token, TokenElevationClass, elevationBuffer, sizeof(uint), out var returned)
                    || returned < sizeof(uint))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query peer token elevation.");
                elevated = Marshal.ReadInt32(elevationBuffer) != 0;
            }
            finally { Marshal.FreeHGlobal(elevationBuffer); }

            return new WindowsTokenIdentityInfo(sid, authenticationId, sessionId, elevated);
        }
    }

    private static IntPtr QueryTokenBuffer(SafeAccessTokenHandle token, int informationClass)
    {
        _ = Native.GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out var required);
        if (required == 0 || required > 1024 * 1024)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Windows returned an invalid peer token buffer size.");
        var buffer = Marshal.AllocHGlobal(checked((int)required));
        if (!Native.GetTokenInformation(token, informationClass, buffer, required, out var returned) || returned < required)
        {
            Marshal.FreeHGlobal(buffer);
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not read named-pipe peer token.");
        }
        return buffer;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenUser { public IntPtr UserSid; public uint Attributes; }

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid { public uint LowPart; public int HighPart; }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenStatistics
    {
        public Luid TokenId;
        public Luid AuthenticationId;
        public long ExpirationTime;
        public int TokenType;
        public int ImpersonationLevel;
        public uint DynamicCharged;
        public uint DynamicAvailable;
        public uint GroupCount;
        public uint PrivilegeCount;
        public Luid ModifiedId;
    }

    private sealed class SafeProcessHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeProcessHandle() : base(true) { }
        protected override bool ReleaseHandle() => Native.CloseHandle(handle);
    }

    private static class Native
    {
        [DllImport("kernel32.dll")]
        internal static extern IntPtr GetCurrentProcess();

        [DllImport("kernel32.dll", SetLastError = true)]
        internal static extern SafeProcessHandle OpenProcess(uint access, [MarshalAs(UnmanagedType.Bool)] bool inherit, uint processId);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool OpenProcessToken(SafeProcessHandle process, uint access, out SafeAccessTokenHandle token);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetTokenInformation(
            SafeAccessTokenHandle token, int informationClass, IntPtr information, uint length, out uint returned);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetNamedPipeClientProcessId(SafePipeHandle pipe, out uint clientProcessId);
        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetNamedPipeServerProcessId(SafePipeHandle pipe, out uint serverProcessId);

        [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true,
            EntryPoint = "QueryFullProcessImageNameW")]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool QueryFullProcessImageName(
            SafeProcessHandle process, uint flags, StringBuilder imageName, ref int size);

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(IntPtr handle);
    }
}
