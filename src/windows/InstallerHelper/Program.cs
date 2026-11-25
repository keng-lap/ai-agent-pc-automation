using System.Security.Cryptography;
using System.Text.Json;
using InstallerHelper.Security;

if (!OperatingSystem.IsWindows())
    return Fail("platform_unsupported");

try
{
    var options = HelperOptions.Parse(args);
    var policy = ProtectedInstallPolicy.Load();
    WindowsSecurity.RequireElevatedTokenForSid(options.RequesterSid);

    var helperPath = Path.GetFullPath(Environment.ProcessPath
        ?? throw new InvalidOperationException("Helper executable path is unavailable."));
    if (!StringComparer.OrdinalIgnoreCase.Equals(helperPath, Path.GetFullPath(policy.HelperPath)))
        throw new CryptographicException("Running Helper path does not match the protected install policy.");

    // Verify the executable itself against the policy reloaded from the fixed,
    // administrator-protected Program Files location.
    WindowsSecurity.RequireTrustedAuthenticodeSignature(helperPath, policy.CertificateSha256);

    var identity = WindowsTokenIdentity.GetCurrentProcessIdentity();
    if (!StringComparer.Ordinal.Equals(identity.UserSid, options.RequesterSid)
        || !StringComparer.Ordinal.Equals(identity.AuthenticationId, options.RequesterLogonId)
        || identity.SessionId != options.RequesterSessionId
        || !identity.IsElevated)
        throw new UnauthorizedAccessException("Elevated Helper token does not match the requesting logon session.");

    using var server = WindowsSecureNamedPipeServer.Create(options.TicketId, options.RequesterSid);
    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(30));
    await WindowsSecureNamedPipeServer.WaitForApprovedClientAsync(
        server,
        new WindowsTokenIdentityInfo(options.RequesterSid, options.RequesterLogonId, options.RequesterSessionId, false),
        timeout.Token);

    var frame = await InstallerHelperPipeProtocol.ReadFrameAsync(server, timeout.Token);
    var request = JsonSerializer.Deserialize<HelperRequest>(frame)
        ?? throw new InvalidDataException("Helper request payload is empty.");

    if (!StringComparer.Ordinal.Equals(request.Ticket.TicketId, options.TicketId))
        throw new CryptographicException("Ticket ID does not match the named pipe.");
    if (!StringComparer.Ordinal.Equals(request.Ticket.RequesterSid, options.RequesterSid)
        || !StringComparer.Ordinal.Equals(request.Ticket.RequesterLogonId, options.RequesterLogonId)
        || request.Ticket.RequesterSessionId != options.RequesterSessionId)
        throw new CryptographicException("Ticket requester identity does not match the UAC request.");

    var keyStore = new ProtectedApprovalKeyStore(policy.ProtectedStoreDirectory);
    var key = keyStore.LoadExisting();
    try
    {
        var now = DateTimeOffset.UtcNow;
        request.Ticket.Verify(
            key,
            options.RequesterSid,
            options.RequesterLogonId,
            options.RequesterSessionId,
            request.Ticket.ApprovalDigest,
            now);
    }
    finally
    {
        CryptographicOperations.ZeroMemory(key);
    }

    // The protected policy closes the CLI trust-anchor substitution gap.
    // Execution remains denied until Backend reservation and staged-installer
    // identity are independently verified by the Helper.
    var response = JsonSerializer.SerializeToUtf8Bytes(new HelperResponse(
        "DENIED_NOT_READY",
        "execution_binding_not_implemented"));
    await InstallerHelperPipeProtocol.WriteFrameAsync(server, response, timeout.Token);
    return 12;
}
catch (OperationCanceledException)
{
    return Fail("client_timeout_or_disconnect");
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Installer Helper denied request: {ex.GetType().Name}");
    return 10;
}

static int Fail(string code)
{
    Console.Error.WriteLine($"Installer Helper: {code}");
    return 10;
}

internal sealed record HelperRequest(InstallerApprovalTicket Ticket);
internal sealed record HelperResponse(string Status, string Reason);

internal sealed record HelperOptions(
    string TicketId,
    string RequesterSid,
    string RequesterLogonId,
    int RequesterSessionId)
{
    public static HelperOptions Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < args.Length; i += 2)
        {
            if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Invalid Helper arguments.");
            values.Add(args[i][2..], args[i + 1]);
        }

        string Required(string key) =>
            values.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value)
                ? value
                : throw new ArgumentException($"Missing --{key}.");

        if (values.Keys.Any(key => key is not ("ticket-id" or "requester-sid" or "requester-logon-id" or "requester-session-id")))
            throw new ArgumentException("Unexpected Helper argument.");

        if (!int.TryParse(Required("requester-session-id"), out var sessionId) || sessionId < 0)
            throw new ArgumentException("Requester session ID is invalid.");

        var ticketId = Required("ticket-id");
        if (ticketId.Length != 32 || ticketId.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Ticket ID is invalid.");
        var logonId = Required("requester-logon-id");
        if (logonId.Length != 16 || logonId.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Requester logon ID is invalid.");
        var sid = Required("requester-sid");
        if (sid.Length > 184 || !sid.StartsWith("S-1-", StringComparison.Ordinal))
            throw new ArgumentException("Requester SID is invalid.");

        return new HelperOptions(ticketId, sid, logonId, sessionId);
    }
}
