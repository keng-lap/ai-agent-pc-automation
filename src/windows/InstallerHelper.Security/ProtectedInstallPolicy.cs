using System.Security.AccessControl;
using System.Security.Cryptography;
using System.Security.Principal;
using System.Text.Json;

namespace InstallerHelper.Security;

/// <summary>
/// Reads the machine-installed trust policy from a fixed Program Files location.
/// The policy is readable by standard users but writable only by SYSTEM and
/// Administrators. Runtime components never accept trust anchors from CLI input.
/// </summary>
public sealed record ProtectedInstallPolicy(
    string HelperPath,
    string CertificateSha256,
    string ProtectedStoreDirectory,
    string NonceDirectory)
{
    private const string ProductDirectoryName = "AI Agent PC Automation";
    private const string SecurityDirectoryName = "Security";
    private const string PolicyFileName = "install-policy.json";
    private static readonly SecurityIdentifier SystemSid = new(WellKnownSidType.LocalSystemSid, null);
    private static readonly SecurityIdentifier AdministratorsSid = new(WellKnownSidType.BuiltinAdministratorsSid, null);
    private static readonly SecurityIdentifier UsersSid = new(WellKnownSidType.BuiltinUsersSid, null);

    public static string FixedPolicyPath
    {
        get
        {
            var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
            if (string.IsNullOrWhiteSpace(programFiles))
                throw new DirectoryNotFoundException("Program Files location is unavailable.");
            return Path.Combine(programFiles, ProductDirectoryName, SecurityDirectoryName, PolicyFileName);
        }
    }

    public static ProtectedInstallPolicy Load()
    {
        if (!OperatingSystem.IsWindows())
            throw new PlatformNotSupportedException("Protected install policy is Windows-only.");

        var path = FixedPolicyPath;
        var directory = Path.GetDirectoryName(path)
            ?? throw new InvalidOperationException("Protected policy directory is invalid.");
        VerifyNotReparsePoint(directory, "policy directory");
        VerifyPolicyDirectory(directory);
        VerifyPolicyFile(path);

        var json = File.ReadAllBytes(path);
        if (json.Length is <= 0 or > 16 * 1024)
            throw new CryptographicException("Protected install policy size is invalid.");

        var policy = JsonSerializer.Deserialize<ProtectedInstallPolicy>(
            json,
            new JsonSerializerOptions { PropertyNameCaseInsensitive = false })
            ?? throw new CryptographicException("Protected install policy is empty.");

        policy.ValidateValues();
        policy.VerifyInstalledHelper();
        return policy;
    }

    private void VerifyInstalledHelper()
    {
        var helperPath = Path.GetFullPath(HelperPath);
        var helperDirectory = Path.GetDirectoryName(helperPath)
            ?? throw new CryptographicException("Installed Helper directory is invalid.");
        VerifyNotReparsePoint(helperDirectory, "Helper directory");
        VerifyPolicyDirectory(helperDirectory);
        VerifyPolicyFile(helperPath);
    }
    private void ValidateValues()
    {
        if (!Path.IsPathFullyQualified(HelperPath)
            || !Path.IsPathFullyQualified(ProtectedStoreDirectory)
            || !Path.IsPathFullyQualified(NonceDirectory))
            throw new CryptographicException("Protected install policy paths must be absolute.");

        if (CertificateSha256.Length != 64 || CertificateSha256.Any(c => !Uri.IsHexDigit(c)))
            throw new CryptographicException("Protected install policy certificate pin is invalid.");

        var helper = Path.GetFullPath(HelperPath);
        var expectedRoot = Path.GetFullPath(Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles),
            ProductDirectoryName)) + Path.DirectorySeparatorChar;
        if (!helper.StartsWith(expectedRoot, StringComparison.OrdinalIgnoreCase)
            || !StringComparer.OrdinalIgnoreCase.Equals(Path.GetFileName(helper), "InstallerHelper.exe"))
            throw new CryptographicException("Protected Helper path must be the installed product Helper under Program Files.");

        if (!Path.GetFullPath(ProtectedStoreDirectory).StartsWith(
                Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), ProductDirectoryName)) + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase)
            || !Path.GetFullPath(NonceDirectory).StartsWith(
                Path.GetFullPath(Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData), ProductDirectoryName)) + Path.DirectorySeparatorChar,
                StringComparison.OrdinalIgnoreCase))
            throw new CryptographicException("Protected approval stores must be under the product ProgramData directory.");
    }

    private static void VerifyNotReparsePoint(string path, string description)
    {
        var info = new DirectoryInfo(path);
        if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException($"Protected {description} is missing or is a reparse point.");
    }

    private static void VerifyPolicyDirectory(string path)
    {
        var info = new DirectoryInfo(path);
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "policy directory");
    }

    private static void VerifyPolicyFile(string path)
    {
        var info = new FileInfo(path);
        if (!info.Exists || (info.Attributes & FileAttributes.ReparsePoint) != 0)
            throw new CryptographicException("Protected install policy is missing or is a reparse point.");
        VerifyAcl(info.GetAccessControl(AccessControlSections.Access | AccessControlSections.Owner), "install policy");
    }

    private static void VerifyAcl(FileSystemSecurity security, string description)
    {
        if (!security.AreAccessRulesProtected)
            throw new CryptographicException($"Protected {description} DACL must not inherit permissions.");

        var owner = security.GetOwner(typeof(SecurityIdentifier)) as SecurityIdentifier;
        if (owner is null || (!owner.Equals(SystemSid) && !owner.Equals(AdministratorsSid)))
            throw new CryptographicException($"Protected {description} owner must be SYSTEM or Administrators.");

        foreach (AuthorizationRule rule in security.GetAccessRules(
                     includeExplicit: true, includeInherited: true, targetType: typeof(SecurityIdentifier)))
        {
            if (rule is not FileSystemAccessRule access)
                throw new CryptographicException($"Protected {description} contains an unsupported ACL rule.");
            if (access.AccessControlType != AccessControlType.Allow)
                throw new CryptographicException($"Protected {description} must not contain deny ACL rules.");

            var sid = (SecurityIdentifier)access.IdentityReference;
            var rights = access.FileSystemRights;
            if (sid.Equals(SystemSid) || sid.Equals(AdministratorsSid))
            {
                if ((rights & FileSystemRights.FullControl) != FileSystemRights.FullControl)
                    throw new CryptographicException($"SYSTEM and Administrators require full control of {description}.");
            }
            else if (sid.Equals(UsersSid))
            {
                var writeRights = FileSystemRights.Write | FileSystemRights.Modify | FileSystemRights.Delete
                    | FileSystemRights.ChangePermissions | FileSystemRights.TakeOwnership | FileSystemRights.FullControl;
                if ((rights & writeRights) != 0
                    || (rights & FileSystemRights.ReadAndExecute) != FileSystemRights.ReadAndExecute)
                    throw new CryptographicException($"Standard Users may read but must not modify {description}.");
            }
            else
            {
                throw new CryptographicException($"Protected {description} grants access to an unexpected principal.");
            }
        }
    }
}
