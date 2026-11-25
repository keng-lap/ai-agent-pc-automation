using System.Security.Cryptography;
using System.Text.Json;
using InstallerHelper.Security;

if (!OperatingSystem.IsWindows())
    return Fail("platform_unsupported");

try
{
    var options = HelperOptions.Parse(args);
    WindowsSecurity.RequireElevatedTokenForSid(options.RequesterSid);

    // The executable itself must be signed by the explicitly enrolled project
    // certificate. This is checked again by the unelevated Launcher.
    WindowsSecurity.RequireTrustedAuthenticodeSignature(
        Environment.ProcessPath ?? throw new InvalidOperationException("Helper executable path is unavailable."),
        options.CertificateSha256);

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

    var keyStore = new ProtectedApprovalKeyStore(options.ProtectedStoreDirectory);
    var key = keyStore.LoadOrCreate();
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

        var nonceStore = new DurableNonceStore(options.ProtectedStoreDirectory);
        nonceStore.Consume(
            request.Ticket.Nonce,
            request.Ticket.TicketId,
            DateTimeOffset.FromUnixTimeSeconds(request.Ticket.ExpiresAtUnixSeconds),
            now);
    }
    finally
    {
        CryptographicOperations.ZeroMemory(key);
    }

    // Deliberately no installer launch in this bootstrap. A reservation-to-ticket
    // signer and verified staged-installer binding must be wired before execution
    // can be enabled. Consuming an otherwise valid ticket without those bindings
    // fails closed and never creates an installer process.
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
    int RequesterSessionId,
    string CertificateSha256,
    string ProtectedStoreDirectory)
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

        if (!int.TryParse(Required("requester-session-id"), out var sessionId) || sessionId < 0)
            throw new ArgumentException("Requester session ID is invalid.");

        var ticketId = Required("ticket-id");
        if (ticketId.Length != 32 || ticketId.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Ticket ID is invalid.");
        var logonId = Required("requester-logon-id");
        if (logonId.Length != 16 || logonId.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Requester logon ID is invalid.");
        var pin = Required("certificate-sha256");
        if (pin.Length != 64 || pin.Any(c => !Uri.IsHexDigit(c)))
            throw new ArgumentException("Certificate pin is invalid.");

        return new HelperOptions(
            ticketId,
            Required("requester-sid"),
            logonId,
            sessionId,
            pin,
            Required("protected-store"));
    }
}
