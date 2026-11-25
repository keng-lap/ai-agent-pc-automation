using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;

namespace InstallerHelper.Security;

/// <summary>
/// Protects the 256-bit approval-ticket HMAC key with machine-scope Windows DPAPI.
/// The resulting blob MUST be stored in an administrator-protected directory:
/// LocalMachine DPAPI does not by itself restrict which local users can decrypt
/// a blob they can read.
/// </summary>
public static class DpapiApprovalKeyProtector
{
    private const uint CryptProtectLocalMachine = 0x4;
    private const int MinimumKeyLength = 32;
    private const int MaximumProtectedBlobLength = 16 * 1024;
    private static readonly byte[] Entropy = SHA256.HashData(
        Encoding.UTF8.GetBytes("keng-lap/ai-agent-pc-automation/InstallerHelper/ApprovalTicketKey/v1"));

    public static byte[] Protect(ReadOnlySpan<byte> key)
    {
        EnsureWindows();
        if (key.Length < MinimumKeyLength)
            throw new CryptographicException("Approval HMAC key must contain at least 256 bits.");

        var input = CreateBlob(key);
        var entropy = CreateBlob(Entropy);
        DataBlob output = default;
        try
        {
            if (!Native.CryptProtectData(
                ref input, "Installer Helper approval ticket key", ref entropy,
                IntPtr.Zero, IntPtr.Zero, CryptProtectLocalMachine, out output))
                throw new Win32Exception(Marshal.GetLastWin32Error(), "DPAPI could not protect the approval key.");
            if (output.Length <= 0 || output.Length > MaximumProtectedBlobLength)
                throw new CryptographicException("DPAPI returned an invalid protected-key length.");
            var protectedBytes = new byte[output.Length];
            Marshal.Copy(output.Data, protectedBytes, 0, output.Length);
            return protectedBytes;
        }
        finally
        {
            ZeroAndFree(input);
            ZeroAndFree(entropy);
            ZeroAndLocalFree(output);
        }
    }

    public static byte[] Unprotect(ReadOnlySpan<byte> protectedKey)
    {
        EnsureWindows();
        if (protectedKey.Length is < 1 or > MaximumProtectedBlobLength)
            throw new CryptographicException("Protected approval key blob has an invalid length.");

        var input = CreateBlob(protectedKey);
        var entropy = CreateBlob(Entropy);
        DataBlob output = default;
        IntPtr description = IntPtr.Zero;
        try
        {
            if (!Native.CryptUnprotectData(
                ref input, out description, ref entropy,
                IntPtr.Zero, IntPtr.Zero, 0, out output))
                throw new CryptographicException(
                    "DPAPI could not unprotect the approval key.",
                    new Win32Exception(Marshal.GetLastWin32Error()));
            if (output.Length != MinimumKeyLength)
                throw new CryptographicException("Unprotected approval key must be exactly 256 bits.");
            var key = new byte[output.Length];
            Marshal.Copy(output.Data, key, 0, output.Length);
            return key;
        }
        finally
        {
            ZeroAndFree(input);
            ZeroAndFree(entropy);
            ZeroAndFree(output);
            if (description != IntPtr.Zero)
                Native.LocalFree(description);
        }
    }

    private static void EnsureWindows()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Approval key protection requires Windows DPAPI.");
    }

    private static DataBlob CreateBlob(ReadOnlySpan<byte> value)
    {
        var pointer = Marshal.AllocHGlobal(value.Length);
        Marshal.Copy(value.ToArray(), 0, pointer, value.Length);
        return new DataBlob { Length = value.Length, Data = pointer };
    }

    private static void ZeroAndFree(DataBlob blob)
    {
        if (blob.Data == IntPtr.Zero)
            return;
        if (blob.Length > 0)
            Marshal.Copy(new byte[blob.Length], 0, blob.Data, blob.Length);
        Marshal.FreeHGlobal(blob.Data);
    }

    private static void ZeroAndLocalFree(DataBlob blob)
    {
        if (blob.Data == IntPtr.Zero)
            return;
        if (blob.Length > 0)
            Marshal.Copy(new byte[blob.Length], 0, blob.Data, blob.Length);
        Native.LocalFree(blob.Data);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct DataBlob
    {
        public int Length;
        public IntPtr Data;
    }

    private static class Native
    {
        [DllImport("crypt32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CryptProtectData(
            ref DataBlob dataIn,
            string description,
            ref DataBlob optionalEntropy,
            IntPtr reserved,
            IntPtr prompt,
            uint flags,
            out DataBlob dataOut);

        [DllImport("crypt32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
        [return: MarshalAs(UnmanagedType.Bool)]
        internal static extern bool CryptUnprotectData(
            ref DataBlob dataIn,
            out IntPtr description,
            ref DataBlob optionalEntropy,
            IntPtr reserved,
            IntPtr prompt,
            uint flags,
            out DataBlob dataOut);

        [DllImport("kernel32.dll")]
        internal static extern IntPtr LocalFree(IntPtr memory);
    }
}
