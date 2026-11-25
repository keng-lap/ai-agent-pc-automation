using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;

namespace InstallerHelper.Security;

/// <summary>
/// Stores the DPAPI-protected approval HMAC key in a directory whose DACL is
/// explicitly restricted to LocalSystem and the local Administrators group.
/// Provisioning is an explicit elevated setup action; runtime access always
/// re-audits the directory and key-file ACLs before reading or writing secrets.
/// </summary>
public sealed class ProtectedApprovalKeyStore
{
    private const string KeyFileName = "approval-ticket-key.dpapi";
    private static readonly SecurityIdentifier SystemSid = new(WellKnownSidType.LocalSystemSid, null);
    private static readonly SecurityIdentifier AdministratorsSid = new(WellKnownSidType.BuiltinAdministratorsSid, null);
    private readonly string _directoryPath;
    private readonly string _keyPath;

    public ProtectedApprovalKeyStore(string directoryPath)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Protected approval key storage is Windows-only.");
        if (string.IsNullOrWhiteSpace(directoryPath) || !Path.IsPathFullyQualified(directoryPath))
            throw new ArgumentException("Key store directory must be an absolute path.", nameof(directoryPath));

        _directoryPath = Path.GetFullPath(directoryPath);
        _keyPath = Path.Combine(_directoryPath, KeyFileName);
        VerifyDirectory();
    }

    /// <summary>
    /// Creates or hardens the product-owned directory. Must be called by an
    /// explicitly elevated installer/setup process, never by the Backend.
    /// </summary>
    public static void ProvisionDirectory(string directoryPath)
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Protected approval key storage is Windows-only.");
        if (string.IsNullOrWhiteSpace(directoryPath) || !Path.IsPathFullyQualified(directoryPath))
            throw new ArgumentException("Key store directory must be an absolute path.", nameof(directoryPath));

        using var identity = WindowsIdentity.GetCurrent();
        var sid = identity.User?.Value ?? throw new UnauthorizedAccessException("Current Windows SID is unavailable.");
        WindowsSecurity.RequireElevatedTokenForSid(sid);

        var fullPath = Path.GetFullPath(directoryPath);
        Directory.CreateDirectory(fullPath);
        var info = new DirectoryInfo(fullPath);
        if ((info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException("Key store directory must not be a reparse point.");

        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(AdministratorsSid);
        security.AddAccessRule(new FileSystemAccessRule(
            SystemSid, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(
            AdministratorsSid, FileSystemRights.FullControl, InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit,
            PropagationFlags.None, AccessControlType.Allow));
        info.SetAccessControl(security);
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "directory");
    }

    /// <summary>
    /// Loads the existing 256-bit key or atomically creates it. The caller owns
    /// the returned bytes and must zero them after use.
    /// </summary>
    public byte[] LoadOrCreate()
    {
        VerifyDirectory();
        if (File.Exists(_keyPath))
        {
            VerifyKeyFile();
            var protectedBytes = File.ReadAllBytes(_keyPath);
            try
            {
                return DpapiApprovalKeyProtector.Unprotect(protectedBytes);
            }
            finally
            {
                CryptographicOperations.ZeroMemory(protectedBytes);
            }
        }

        var key = RandomNumberGenerator.GetBytes(32);
        var protectedKey = DpapiApprovalKeyProtector.Protect(key);
        var temporaryPath = Path.Combine(_directoryPath, ".approval-key-" + Guid.NewGuid().ToString("N") + ".tmp");
        try
        {
            // Prepare the temporary file's restrictive DACL before writing any secret.
            using (var stream = new FileStream(
                temporaryPath, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                4096, FileOptions.WriteThrough))
            {
                ApplyKeyFileAcl(temporaryPath);
                stream.Write(protectedKey);
                stream.Flush(flushToDisk: true);
            }

            try
            {
                // Same-volume rename publishes only a complete, flushed ciphertext.
                File.Move(temporaryPath, _keyPath);
                VerifyKeyFile();
                return key;
            }
            catch (IOException) when (File.Exists(_keyPath))
            {
                CryptographicOperations.ZeroMemory(key);
                VerifyKeyFile();
                var winnerBlob = File.ReadAllBytes(_keyPath);
                try { return DpapiApprovalKeyProtector.Unprotect(winnerBlob); }
                finally { CryptographicOperations.ZeroMemory(winnerBlob); }
            }
        }
        catch
        {
            CryptographicOperations.ZeroMemory(key);
            throw;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(protectedKey);
            try { if (File.Exists(temporaryPath)) File.Delete(temporaryPath); } catch { /* stale temp is never loaded */ }
        }
    }

    /// <summary>
    /// Loads an already provisioned key without creating or rotating it. Elevated
    /// runtime components must use this method so a missing setup-time key fails closed.
    /// </summary>
    public byte[] LoadExisting()
    {
        VerifyDirectory();
        VerifyKeyFile();
        var protectedBytes = File.ReadAllBytes(_keyPath);
        try
        {
            var key = DpapiApprovalKeyProtector.Unprotect(protectedBytes);
            if (key.Length != 32)
            {
                CryptographicOperations.ZeroMemory(key);
                throw new CryptographicException("Provisioned approval key must be exactly 256 bits.");
            }
            return key;
        }
        finally
        {
            CryptographicOperations.ZeroMemory(protectedBytes);
        }
    }

    private void VerifyDirectory()
    {
        var info = new DirectoryInfo(_directoryPath);
        if (!info.Exists)
            throw new DirectoryNotFoundException("Protected approval key directory has not been provisioned.");
        if ((info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException("Protected approval key directory must not be a reparse point.");
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "directory");
    }

    private void VerifyKeyFile()
    {
        var info = new FileInfo(_keyPath);
        if (!info.Exists)
            throw new FileNotFoundException("Protected approval key file is missing.", _keyPath);
        if ((info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException("Protected approval key file must not be a reparse point.");
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "key file");
    }

    private static void ApplyKeyFileAcl(string path)
    {
        var security = new FileSecurity();
        security.SetAccessRuleProtection(isProtected: true, preserveInheritance: false);
        security.SetOwner(AdministratorsSid);
        security.AddAccessRule(new FileSystemAccessRule(SystemSid, FileSystemRights.FullControl, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(AdministratorsSid, FileSystemRights.FullControl, AccessControlType.Allow));
        new FileInfo(path).SetAccessControl(security);
        var info = new FileInfo(path);
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "key file");
    }

    private static void VerifyAcl(FileSystemSecurity security, string description)
    {
        if (!security.AreAccessRulesProtected)
            throw new CryptographicException($"Protected approval {description} DACL must not inherit permissions.");
        var owner = security.GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier;
        if (owner is null || (!owner.Equals(SystemSid) && !owner.Equals(AdministratorsSid)))
            throw new CryptographicException($"Protected approval {description} owner must be SYSTEM or Administrators.");

        var rules = security.GetAccessRules(includeExplicit: true, includeInherited: true, targetType: typeof(SecurityIdentifier));
        foreach (AuthorizationRule rule in rules)
        {
            if (rule is not FileSystemAccessRule accessRule || accessRule.AccessControlType != AccessControlType.Allow)
                continue;
            var sid = (SecurityIdentifier)accessRule.IdentityReference;
            if (!sid.Equals(SystemSid) && !sid.Equals(AdministratorsSid))
                throw new CryptographicException($"Protected approval {description} grants access to an untrusted principal: {sid.Value}.");
        }
    }
}
