using System.ComponentModel;
using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text.Json;
using InstallerHelper.Security;

if (!OperatingSystem.IsWindows())
    return Fail("platform_unsupported");

try
{
    var options = LauncherOptions.Parse(args);
    var requester = WindowsTokenIdentity.GetCurrentProcessIdentity();
    if (requester.IsElevated)
        throw new UnauthorizedAccessException("Launcher must run with a non-elevated token.");

    var helperPath = Path.GetFullPath(options.HelperPath);
    if (!File.Exists(helperPath))
        throw new FileNotFoundException("Installed Helper executable was not found.", helperPath);
    WindowsSecurity.RequireTrustedAuthenticodeSignature(helperPath, options.CertificateSha256);

    var ticketBytes = await File.ReadAllBytesAsync(options.TicketFile);
    if (ticketBytes.Length is <= 0 or > InstallerHelperPipeProtocol.MaximumFrameBytes)
        throw new InvalidDataException("Approval ticket file is outside the permitted size.");
    var request = JsonSerializer.Deserialize<LauncherRequest>(ticketBytes)
        ?? throw new InvalidDataException("Approval ticket file is invalid.");
    var ticket = request.Ticket;

    if (!StringComparer.Ordinal.Equals(ticket.RequesterSid, requester.UserSid)
        || !StringComparer.Ordinal.Equals(ticket.RequesterLogonId, requester.AuthenticationId)
        || ticket.RequesterSessionId != requester.SessionId
        || !StringComparer.Ordinal.Equals(ticket.TicketId, Path.GetFileNameWithoutExtension(options.TicketFile)))
        throw new CryptographicException("Approval ticket is not bound to the current Windows logon session.");

    var protectedStore = Path.GetFullPath(options.ProtectedStoreDirectory);
    var helperArguments = string.Join(" ", new[]
    {
        "--ticket-id", Quote(ticket.TicketId),
        "--requester-sid", Quote(requester.UserSid),
        "--requester-logon-id", Quote(requester.AuthenticationId),
        "--requester-session-id", requester.SessionId.ToString(System.Globalization.CultureInfo.InvariantCulture),
        "--certificate-sha256", Quote(options.CertificateSha256),
        "--protected-store", Quote(protectedStore)
    });

    // ShellExecute "runas" is the only elevation boundary. ERROR_CANCELLED (1223)
    // is handled as a terminal denial; no pipe connection or installer is started.
    using var helper = new Process
    {
        StartInfo = new ProcessStartInfo
        {
            FileName = helperPath,
            Arguments = helperArguments,
            Verb = "runas",
            UseShellExecute = true,
            WorkingDirectory = Path.GetDirectoryName(helperPath)!
        }
    };

    try
    {
        if (!helper.Start())
            return Fail("uac_launch_failed");
    }
    catch (Win32Exception ex) when (ex.NativeErrorCode == 1223)
    {
        return Fail("uac_cancelled_no_install_started");
    }

    using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(35));
    using var client = new NamedPipeClientStream(
        ".",
        WindowsNamedPipePeerVerifier.CreatePipeName(ticket.TicketId),
        PipeDirection.InOut,
        PipeOptions.Asynchronous);

    await client.ConnectAsync(timeout.Token);
    WindowsNamedPipePeerVerifier.RequireServerIdentity(
        client.SafePipeHandle,
        requester.UserSid,
        requester.AuthenticationId,
        requester.SessionId,
        helperPath,
        options.CertificateSha256);

    await InstallerHelperPipeProtocol.WriteFrameAsync(client, ticketBytes, timeout.Token);
    var responseBytes = await InstallerHelperPipeProtocol.ReadFrameAsync(client, timeout.Token);
    var response = JsonSerializer.Deserialize<LauncherResponse>(responseBytes)
        ?? throw new InvalidDataException("Helper response is invalid.");

    Console.WriteLine(JsonSerializer.Serialize(response));
    return StringComparer.Ordinal.Equals(response.Status, "ACCEPTED") ? 0 : 12;
}
catch (OperationCanceledException)
{
    return Fail("helper_timeout_no_install_started");
}
catch (Exception ex)
{
    Console.Error.WriteLine($"Launcher denied request: {ex.GetType().Name}");
    return 10;
}

static int Fail(string code)
{
    Console.Error.WriteLine(code);
    return code == "uac_cancelled_no_install_started" ? 1223 : 10;
}

static string Quote(string value) => "\"" + value.Replace("\\", "\\\\").Replace("\"", "\\\"") + "\"";

internal sealed record LauncherRequest(InstallerApprovalTicket Ticket);
internal sealed record LauncherResponse(string Status, string Reason);

internal sealed record LauncherOptions(
    string HelperPath,
    string TicketFile,
    string CertificateSha256,
    string ProtectedStoreDirectory)
{
    public static LauncherOptions Parse(string[] args)
    {
        var values = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        for (var i = 0; i < args.Length; i += 2)
        {
            if (i + 1 >= args.Length || !args[i].StartsWith("--", StringComparison.Ordinal))
                throw new ArgumentException("Invalid Launcher arguments.");
            values.Add(args[i][2..], args[i + 1]);
        }
        string Required(string key) =>
            values.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value)
                ? value
                : throw new ArgumentException($"Missing --{key}.");
        return new LauncherOptions(
            Required("helper"),
            Required("ticket-file"),
            Required("certificate-sha256"),
            Required("protected-store"));
    }
}
