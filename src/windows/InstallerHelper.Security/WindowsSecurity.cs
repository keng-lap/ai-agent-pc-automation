using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Security.Cryptography.X509Certificates;
using Microsoft.Win32.SafeHandles;

namespace InstallerHelper.Security;

/// <summary>
/// Windows-only security primitives for the future elevated installer helper.
/// These APIs deliberately do not launch processes or perform installations.
/// </summary>
public static class WindowsSecurity
{
    public static void RequireElevatedTokenForSid(string expectedUserSid)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("The installer helper is Windows-only.");

        if (string.IsNullOrWhiteSpace(expectedUserSid))
            throw new ArgumentException("An expected Windows SID is required.", nameof(expectedUserSid));

        using var token = OpenCurrentProcessToken();
        var elevation = new TokenElevation();
        if (!NativeMethods.GetTokenInformation(
                token, TokenInformationClass.TokenElevation,
                ref elevation, (uint)Marshal.SizeOf<TokenElevation>(), out var returned)
            || returned < Marshal.SizeOf<TokenElevation>())
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not verify the effective token elevation.");

        if (elevation.TokenIsElevated == 0)
            throw new UnauthorizedAccessException("Elevated Installer Helper requires an elevated Windows token.");

        using var identity = WindowsIdentity.GetCurrent();
        var actualSid = identity.User?.Value;
        if (!StringComparer.Ordinal.Equals(actualSid, expectedUserSid))
            throw new UnauthorizedAccessException("The elevated token SID does not match the approving Windows user.");
    }

    public static void RequireTrustedAuthenticodeSignature(string filePath, string expectedCertificateThumbprint)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Authenticode verification is Windows-only.");
        if (string.IsNullOrWhiteSpace(filePath) || !File.Exists(filePath))
            throw new FileNotFoundException("The signed binary was not found.", filePath);
        if (string.IsNullOrWhiteSpace(expectedCertificateThumbprint))
            throw new ArgumentException("A pinned certificate thumbprint is required.", nameof(expectedCertificateThumbprint));

        var normalizedPin = NormalizeThumbprint(expectedCertificateThumbprint);
        var fileInfo = new WinTrustFileInfo(filePath);
        var trustData = new WinTrustData(fileInfo);
        var action = NativeMethods.WinTrustActionGenericVerifyV2;
        var status = NativeMethods.WinVerifyTrust(IntPtr.Zero, ref action, ref trustData);

        // Always release provider state, including on verification failure.
        trustData.StateAction = WinTrustStateAction.Close;
        _ = NativeMethods.WinVerifyTrust(IntPtr.Zero, ref action, ref trustData);

        if (status != 0)
            throw new CryptographicException($"Authenticode trust verification failed (0x{status:X8}).");

        using var signer = new X509Certificate2(X509Certificate.CreateFromSignedFile(filePath));
        if (!StringComparer.OrdinalIgnoreCase.Equals(NormalizeThumbprint(signer.Thumbprint), normalizedPin))
            throw new CryptographicException("The signed binary certificate does not match the pinned project certificate.");
    }

    private static string NormalizeThumbprint(string value) =>
        new(value.Where(Uri.IsHexDigit).Select(char.ToUpperInvariant).ToArray());

    private static SafeKernelHandle OpenCurrentProcessToken()
    {
        if (!NativeMethods.OpenProcessToken(
                NativeMethods.GetCurrentProcess(), TokenAccessMask.Query, out var token))
            throw new Win32Exception(Marshal.GetLastWin32Error(), "Could not open the current process token.");
        return token;
    }

    private const uint TokenAccessMaskQuery = 0x0008;
    private const int TokenElevationInformationClass = 20;

    private enum TokenInformationClass
    {
        TokenElevation = TokenElevationInformationClass
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct TokenElevation
    {
        public uint TokenIsElevated;
    }

    private enum WinTrustStateAction : uint { Ignore = 0, Verify = 1, Close = 2 }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private sealed class WinTrustFileInfo
    {
        public uint Size;
        [MarshalAs(UnmanagedType.LPWStr)] public string FilePath;
        public IntPtr FileHandle;
        public IntPtr KnownSubject;

        public WinTrustFileInfo(string filePath)
        {
            Size = (uint)Marshal.SizeOf<WinTrustFileInfo>();
            FilePath = Path.GetFullPath(filePath);
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private sealed class WinTrustData
    {
        public uint Size;
        public IntPtr PolicyCallbackData;
        public IntPtr SipClientData;
        public uint UiChoice;
        public uint RevocationChecks;
        public uint UnionChoice;
        public IntPtr FileInfo;
        public WinTrustStateAction StateAction;
        public IntPtr StateData;
        public IntPtr UrlReference;
        public uint ProviderFlags;
        public uint UiContext;
        public IntPtr SignatureSettings;

        public WinTrustData(WinTrustFileInfo fileInfo)
        {
            Size = (uint)Marshal.SizeOf<WinTrustData>();
            UiChoice = 2; // WTD_UI_NONE
            RevocationChecks = 1; // WTD_REVOKE_WHOLECHAIN
            UnionChoice = 1; // WTD_CHOICE_FILE
            FileInfo = Marshal.AllocHGlobal(Marshal.SizeOf<WinTrustFileInfo>());
            Marshal.StructureToPtr(fileInfo, FileInfo, false);
            StateAction = WinTrustStateAction.Verify;
            ProviderFlags = 0x00000080; // WTD_REVOCATION_CHECK_CHAIN_EXCLUDE_ROOT
        }
    }

    private sealed class SafeKernelHandle : SafeHandleZeroOrMinusOneIsInvalid
    {
        private SafeKernelHandle() : base(true) { }
        protected override bool ReleaseHandle() => NativeMethods.CloseHandle(handle);
    }

    private static class NativeMethods
    {
        internal static readonly Guid WinTrustActionGenericVerifyV2 =
            new("00AAC56B-CD44-11D0-8CC2-00C04FC295EE");

        [DllImport("kernel32.dll")]
        internal static extern IntPtr GetCurrentProcess();

        [DllImport("kernel32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CloseHandle(IntPtr handle);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool OpenProcessToken(
            IntPtr processHandle, uint desiredAccess, out SafeKernelHandle tokenHandle);

        [DllImport("advapi32.dll", SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool GetTokenInformation(
            SafeKernelHandle tokenHandle, TokenInformationClass informationClass,
            ref TokenElevation information, uint informationLength, out uint returnLength);

        [DllImport("wintrust.dll", ExactSpelling = true, PreserveSig = true, SetLastError = true)]
        internal static extern int WinVerifyTrust(
            IntPtr windowHandle, ref Guid actionId, [In, Out] ref WinTrustData trustData);
    }
}
