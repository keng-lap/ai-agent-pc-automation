using System.Security.Cryptography;
using System.Text;

namespace InstallerHelper.Security;

/// <summary>
/// Durable, cross-process one-time nonce consumption using atomic file creation.
/// The directory MUST be pre-created in an administrator-protected location
/// whose ACL grants write access only to SYSTEM and Administrators.
/// This class deliberately fails if the directory is missing or is a reparse point.
/// </summary>
public sealed class DurableNonceStore
{
    private const int NonceHexLength = 64;
    private readonly string _directoryPath;

    public DurableNonceStore(string directoryPath)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Durable helper nonce storage is Windows-only.");
        if (string.IsNullOrWhiteSpace(directoryPath) || !Path.IsPathFullyQualified(directoryPath))
            throw new ArgumentException("Nonce store directory must be an absolute path.", nameof(directoryPath));

        _directoryPath = Path.GetFullPath(directoryPath);
        var info = new DirectoryInfo(_directoryPath);
        if (!info.Exists)
            throw new DirectoryNotFoundException("The pre-provisioned protected nonce directory does not exist.");
        if ((info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException("Nonce store directory must not be a reparse point.");
        // The same strict SYSTEM/Administrators-only DACL protects nonce records
        // as well as the DPAPI ciphertext. DPAPI alone is not an access-control boundary.
        _ = new ProtectedApprovalKeyStore(_directoryPath);
    }

    /// <summary>
    /// Atomically consumes a nonce until its ticket expiry. Exactly one caller
    /// across threads/processes can create the nonce record. Existing records
    /// are never overwritten, including after process restart.
    /// </summary>
    public void Consume(string nonce, string ticketId, DateTimeOffset expiresAt, DateTimeOffset now)
    {
        ValidateHex(nonce, nameof(nonce));
        ValidateHex(ticketId, nameof(ticketId), 32);
        if (expiresAt <= now)
            throw new CryptographicException("Approval nonce ticket has expired.");

        var fileName = Convert.ToHexString(SHA256.HashData(Convert.FromHexString(nonce))) + ".nonce";
        var path = Path.Combine(_directoryPath, fileName);
        var record = Encoding.UTF8.GetBytes(
            $"{ticketId.ToUpperInvariant()}\n{expiresAt.ToUnixTimeSeconds()}\n");
        try
        {
            using var stream = new FileStream(
                path,
                FileMode.CreateNew,
                FileAccess.Write,
                FileShare.None,
                bufferSize: 4096,
                options: FileOptions.WriteThrough);
            stream.Write(record);
            stream.Flush(flushToDisk: true);
        }
        catch (IOException) when (File.Exists(path))
        {
            throw new CryptographicException("Approval nonce has already been consumed.");
        }
    }

    private static void ValidateHex(string value, string field, int length = NonceHexLength)
    {
        if (value is null || value.Length != length || value.Any(character => !Uri.IsHexDigit(character)))
            throw new CryptographicException($"Approval nonce field {field} is invalid.");
    }
}
