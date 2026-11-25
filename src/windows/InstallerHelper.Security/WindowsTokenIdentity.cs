using System.ComponentModel;
using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Security.Principal;
using Microsoft.Win32.SafeHandles;

namespace InstallerHelper.Security;

/// <summary>
/// Identity derived from the current process primary access token. AuthenticationId
/// is the logon-session LUID; SessionId is the Windows Terminal Services session.
/// </summary>
public sealed record WindowsTokenIdentityInfo(
    string UserSid,
    string AuthenticationId,
    int SessionId,
    bool IsElevated);

public static class WindowsTokenIdentity
{
    public static WindowsTokenIdentityInfo GetCurrentProcessIdentity()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Windows token identity is Windows-only.");

        if (!Native.OpenProcessToken(Native.GetCurrentProcess(), 0x0008, out var token))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the current process token.");

        using (token)
        {
            var userBuffer = QueryTokenBuffer(token, TokenUserInformationClass);
            string sid;
            try
            {
                var user = Marshal.PtrToStructure<TokenUser>(userBuffer);
                sid = new SecurityIdentifier(user.UserSid).Value;
            }
            finally
            {
                Marshal.FreeHGlobal(userBuffer);
            }

            var sessionBuffer = Marshal.AllocHGlobal(sizeof(int));
            int sessionId;
            try
            {
                if (!Native.GetTokenInformation(token, TokenSessionIdInformationClass,
                    sessionBuffer, sizeof(int), out var returned) || returned < sizeof(int))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query token session ID.");
                sessionId = Marshal.ReadInt32(sessionBuffer);
                if (sessionId < 0)
                    throw new CryptographicException("Token session ID is invalid.");
            }
            finally
            {
                Marshal.FreeHGlobal(sessionBuffer);
            }

            var statisticsBuffer = QueryTokenBuffer(token, TokenStatisticsInformationClass);
            string authenticationId;
            try
            {
                var statistics = Marshal.PtrToStructure<TokenStatistics>(statisticsBuffer);
                var value = ((ulong)(uint)statistics.AuthenticationId.HighPart << 32)
                    | statistics.AuthenticationId.LowPart;
                authenticationId = value.ToString("X16", System.Globalization.CultureInfo.InvariantCulture);
            }
            finally
            {
                Marshal.FreeHGlobal(statisticsBuffer);
            }

            var elevationBuffer = Marshal.AllocHGlobal(sizeof(uint));
            bool elevated;
            try
            {
                if (!Native.GetTokenInformation(token, TokenElevationInformationClass,
                    elevationBuffer, sizeof(uint), out var returned) || returned < sizeof(uint))
                    throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query token elevation.");
                elevated = Marshal.ReadInt32(elevationBuffer) != 0;
            }
            finally
            {
                Marshal.FreeHGlobal(elevationBuffer);
            }

            return new WindowsTokenIdentityInfo(sid, authenticationId, sessionId, elevated);
        }
    }

    private static IntPtr QueryTokenBuffer(SafeAccessTokenHandle token, int informationClass)
    {
        _ = Native.GetTokenInformation(token, informationClass, IntPtr.Zero, 0, out var required);
        if (required == 0 || required > 1024 * 1024)
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Windows returned an invalid token information size.");

        var buffer = Marshal.AllocHGlobal(checked((int)required));
        if (!Native.GetTokenInformation(token, informationClass, buffer, required, out var returned)
            || returned < required)
        {
            Marshal.FreeHGlobal(buffer);
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not query Windows token identity.");
        }
        return buffer;
    }

    private const int TokenUserInformationClass = 1;
    private const int TokenStatisticsInformationClass = 10;
    private const int TokenSessionIdInformationClass = 12;
    private const int TokenElevationInformationClass = 20;

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenUser
    {
        public IntPtr UserSid;
        public uint Attributes;
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct Luid
    {
        public uint LowPart;
        public int HighPart;
    }

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

    private static class Native
    {
        [DllImport("kernel32.dll")]
        internal static extern IntPtr GetCurrentProcess();

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool OpenProcessToken(
            IntPtr processHandle, uint desiredAccess, out SafeAccessTokenHandle tokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetTokenInformation(
            SafeAccessTokenHandle tokenHandle, int informationClass,
            IntPtr information, uint informationLength, out uint returnLength);
    }
}
