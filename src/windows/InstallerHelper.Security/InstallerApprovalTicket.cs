using System.Security.Cryptography;
using System.Text;

namespace InstallerHelper.Security;

/// <summary>
/// Integrity-protected, exact-action authorization envelope for the future
/// Elevated Installer Helper. This primitive does not consume a nonce or
/// establish trust in the key source; callers must use durable one-time
/// reservation state and a protected key-delivery mechanism.
/// </summary>
public sealed record InstallerApprovalTicket(
    int ProtocolVersion,
    string TicketId,
    string RequesterSid,
    string RequesterLogonId,
    int RequesterSessionId,
    string PlanId,
    string ApprovalDigest,
    string PackageId,
    string Version,
    string Architecture,
    string Scope,
    string InstallerSha256,
    string Nonce,
    long IssuedAtUnixSeconds,
    long ExpiresAtUnixSeconds,
    string SignatureSha256)
{
    public const int CurrentProtocolVersion = 2;
    public const long MaximumLifetimeSeconds = 120;

    /// <summary>Returns a copy signed with HMAC-SHA256 using a caller-protected key.</summary>
    public InstallerApprovalTicket Sign(ReadOnlySpan<byte> key)
    {
        ValidateShape();
        ValidateKey(key);
        var signature = HMACSHA256.HashData(key, GetCanonicalPayload());
        return this with { SignatureSha256 = Convert.ToHexString(signature) };
    }

    /// <summary>
    /// Verifies integrity, time bounds, requester identity, and the exact
    /// approved action. Durable nonce consumption must occur separately and
    /// atomically before any privileged side effect.
    /// </summary>
    public void Verify(
        ReadOnlySpan<byte> key,
        string expectedRequesterSid,
        string expectedRequesterLogonId,
        int expectedRequesterSessionId,
        string expectedApprovalDigest,
        DateTimeOffset now)
    {
        ValidateShape();
        ValidateKey(key);
        if (string.IsNullOrWhiteSpace(expectedRequesterSid)
            || !StringComparer.Ordinal.Equals(RequesterSid, expectedRequesterSid))
            throw new CryptographicException("Approval ticket requester SID mismatch.");
        if (!StringComparer.Ordinal.Equals(RequesterLogonId, expectedRequesterLogonId)
            || RequesterSessionId != expectedRequesterSessionId)
            throw new CryptographicException("Approval ticket requester logon session mismatch.");
        if (!FixedHexEquals(ApprovalDigest, expectedApprovalDigest))
            throw new CryptographicException("Approval ticket action digest mismatch.");

        var nowSeconds = now.ToUnixTimeSeconds();
        if (IssuedAtUnixSeconds > nowSeconds + 5
            || ExpiresAtUnixSeconds <= nowSeconds
            || ExpiresAtUnixSeconds <= IssuedAtUnixSeconds
            || ExpiresAtUnixSeconds - IssuedAtUnixSeconds > MaximumLifetimeSeconds)
            throw new CryptographicException("Approval ticket is expired or has an invalid lifetime.");

        var expected = HMACSHA256.HashData(key, GetCanonicalPayload());
        byte[] supplied;
        try
        {
            supplied = Convert.FromHexString(SignatureSha256);
        }
        catch (FormatException)
        {
            throw new CryptographicException("Approval ticket signature encoding is invalid.");
        }

        if (supplied.Length != expected.Length
            || !CryptographicOperations.FixedTimeEquals(supplied, expected))
            throw new CryptographicException("Approval ticket signature is invalid.");
    }

    private byte[] GetCanonicalPayload()
    {
        using var stream = new MemoryStream();
        using var writer = new BinaryWriter(stream, Encoding.UTF8, leaveOpen: true);
        writer.Write(ProtocolVersion);
        WriteString(writer, TicketId);
        WriteString(writer, RequesterSid);
        WriteString(writer, RequesterLogonId);
        writer.Write(RequesterSessionId);
        WriteString(writer, PlanId);
        WriteString(writer, ApprovalDigest);
        WriteString(writer, PackageId);
        WriteString(writer, Version);
        WriteString(writer, Architecture);
        WriteString(writer, Scope);
        WriteString(writer, InstallerSha256);
        WriteString(writer, Nonce);
        writer.Write(IssuedAtUnixSeconds);
        writer.Write(ExpiresAtUnixSeconds);
        writer.Flush();
        return stream.ToArray();
    }

    private void ValidateShape()
    {
        if (ProtocolVersion != CurrentProtocolVersion)
            throw new CryptographicException("Unsupported approval ticket protocol version.");
        RequireHex(TicketId, 32, nameof(TicketId));
        RequireHex(PlanId, 32, nameof(PlanId));
        RequireHex(ApprovalDigest, 64, nameof(ApprovalDigest));
        RequireHex(InstallerSha256, 64, nameof(InstallerSha256));
        RequireHex(Nonce, 64, nameof(Nonce));
        RequireHex(SignatureSha256, 64, nameof(SignatureSha256), allowEmpty: true);
        if (string.IsNullOrWhiteSpace(RequesterSid) || RequesterSid.Length > 184
            || !RequesterSid.StartsWith("S-1-", StringComparison.Ordinal))
            throw new CryptographicException("Approval ticket requester SID is invalid.");
        RequireHex(RequesterLogonId, 16, nameof(RequesterLogonId));
        if (RequesterSessionId < 0)
            throw new CryptographicException("Approval ticket requester session ID is invalid.");
        RequireText(PackageId, 128, nameof(PackageId));
        RequireText(Version, 64, nameof(Version));
        RequireText(Architecture, 16, nameof(Architecture));
        if (!StringComparer.Ordinal.Equals(Scope, "machine"))
            throw new CryptographicException("Elevated approval ticket must be machine-scope.");
        if (IssuedAtUnixSeconds <= 0 || ExpiresAtUnixSeconds <= 0)
            throw new CryptographicException("Approval ticket timestamps are invalid.");
    }

    private static void ValidateKey(ReadOnlySpan<byte> key)
    {
        if (key.Length < 32)
            throw new CryptographicException("Approval ticket HMAC key must contain at least 256 bits.");
    }

    private static void RequireText(string? value, int maximumLength, string field)
    {
        if (string.IsNullOrWhiteSpace(value) || value.Length > maximumLength
            || value.Any(char.IsControl))
            throw new CryptographicException($"Approval ticket field {field} is invalid.");
    }

    private static void RequireHex(string? value, int length, string field, bool allowEmpty = false)
    {
        if (value is null)
            throw new CryptographicException($"Approval ticket field {field} is missing.");
        if (allowEmpty && value.Length == 0)
            return;
        if (value.Length != length || value.Any(character => !Uri.IsHexDigit(character)))
            throw new CryptographicException($"Approval ticket field {field} must be {length} hexadecimal characters.");
    }

    private static bool FixedHexEquals(string left, string right)
    {
        if (right is null || left.Length != right.Length)
            return false;
        try
        {
            return CryptographicOperations.FixedTimeEquals(
                Convert.FromHexString(left), Convert.FromHexString(right));
        }
        catch (FormatException)
        {
            return false;
        }
    }

    private static void WriteString(BinaryWriter writer, string value)
    {
        var bytes = Encoding.UTF8.GetBytes(value);
        writer.Write(bytes.Length);
        writer.Write(bytes);
    }
}
