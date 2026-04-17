import collections
import logging
import math
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 55+ Production-grade IT runbook articles
KB_ARTICLES = [
    {
        "id": "KB-001",
        "title": "VPN Connection Drops and Timeout Issues",
        "category": "network",
        "content": "VPN disconnecting frequently: 1) Check MTU size mismatch. Set MTU to 1400: `netsh interface ipv4 set subinterface \"OpenVPN\" mtu=1400 store=persistent`. 2) Increase keepalive interval in client config: `keepalive 10 60`. 3) Switch from UDP to TCP mode. 4) Review split tunnel config. 5) Check for ISP throttling. 6) Restart VPN service: `Restart-Service -Name OpenVPNService`",
        "tags": ["vpn", "openvpn", "timeout", "keepalive", "mtu", "tunnel"],
        "related": ["KB-002", "KB-012"]
    },
    {
        "id": "KB-002",
        "title": "GlobalProtect VPN Gateway Not Responding",
        "category": "network",
        "content": "If Palo Alto GlobalProtect gateway fails to respond: 1) Ensure portal address is correct (vpn.company.com). 2) Check local firewall blocking IPSec (UDP 500/4500). 3) Reinstall GlobalProtect agent. 4) Run diagnostics: `C:\\Program Files\\Palo Alto Networks\\GlobalProtect\\PanGPA.exe -repair`. 5) Flush DNS: `ipconfig /flushdns`.",
        "tags": ["vpn", "globalprotect", "gateway", "unreachable"],
        "related": ["KB-001"]
    },
    {
        "id": "KB-003",
        "title": "DNS Lookup Failures (NXDOMAIN)",
        "category": "network",
        "content": "To diagnose DNS resolution: 1) Use `nslookup` or `Resolve-DnsName`. 2) Check if local DNS cache is poisoned; run `ipconfig /flushdns`. 3) Ensure DHCP assigned correct DNS servers via `ipconfig /all`. 4) Test fallback DNS (e.g., 8.8.8.8) to rule out internal DNS outage: `ping 8.8.8.8`. 5) Verify hosts file: `C:\\Windows\\System32\\drivers\\etc\\hosts`.",
        "tags": ["dns", "nxdomain", "resolution", "nslookup", "ipconfig"],
        "related": ["KB-004"]
    },
    {
        "id": "KB-004",
        "title": "DHCP Lease Expired / APIPA Address (169.254.x.x)",
        "category": "network",
        "content": "Client stuck on APIPA (169.254.x.x): 1) Network cable unplugged or switch port disabled. 2) Release and renew IP: `ipconfig /release` then `ipconfig /renew`. 3) Restart DHCP Client service: `Restart-Service -Name dhcp`. 4) Verify VLAN assignment on the switch port. 5) Check if DHCP scope is exhausted on the server.",
        "tags": ["dhcp", "apipa", "169.254", "ipconfig", "vlan"],
        "related": ["KB-003"]
    },
    {
        "id": "KB-005",
        "title": "WiFi Authentication Failure (802.1X / RADIUS)",
        "category": "network",
        "content": "Corporate WiFi (802.1X EAP-TLS/PEAP) rejecting client: 1) Verify user password hasn't expired. 2) Check if client certificate is valid and trusted. 3) Push new cert via MDM/GPO. 4) Forget wireless network: `netsh wlan delete profile name=\"CorpWiFi\"`. 5) Check NPS/RADIUS logs for reason code (e.g., NPS Event ID 6273).",
        "tags": ["wifi", "802.1x", "radius", "radius", "peap", "eap-tls", "nps"],
        "related": []
    },
    {
        "id": "KB-006",
        "title": "BGP Session Flapping",
        "category": "network",
        "content": "BGP adjacency flapping: 1) Check physical interface for link flap/errors: `show interfaces GigabitEthernet0/1`. 2) Monitor CPU utilization on the router: `show processes cpu history`. 3) Verify MTU matches on both ends (jumbo frames). 4) Check for hold-time expiration. 5) Investigate route damping: `show ip bgp dampening dampened-paths`.",
        "tags": ["bgp", "flapping", "router", "adjacency", "mtu"],
        "related": ["KB-007"]
    },
    {
        "id": "KB-007",
        "title": "OSPF Neighbor Adjacency Issues",
        "category": "network",
        "content": "OSPF neighbor stuck in EXSTART/EXCHANGE: 1) Usually an MTU mismatch. Verify MTU on directly connected interfaces. 2) Verify OSPF area config. 3) Check subnets match. 4) Ensure no ACL is blocking protocol 89. 5) Verify hello/dead timers: `show ip ospf interface`.",
        "tags": ["ospf", "routing", "exstart", "mtu", "neighbor"],
        "related": ["KB-006"]
    },
    {
        "id": "KB-008",
        "title": "Firewall Rule Blocking Legitimate Traffic (Cisco ASA/Firepower)",
        "category": "network",
        "content": "To diagnose blocked traffic: 1) Run packet tracer: `packet-tracer input INSIDE tcp 10.0.0.5 12345 192.168.1.10 443`. 2) Review ACL hit counts: `show access-list`. 3) Check NAT rules: `show nat detail`. 4) Verify if traffic is dropped by IPS/IDS policy. 5) Look at real-time logs: `logging buffered debugging`.",
        "tags": ["firewall", "blocked", "acl", "asa", "packet-tracer"],
        "related": []
    },
    {
        "id": "KB-009",
        "title": "BSOD: IRQL_NOT_LESS_OR_EQUAL",
        "category": "hardware",
        "content": "Blue Screen (IRQL_NOT_LESS_OR_EQUAL): Usually indicates faulty RAM, driver conflict, or hardware incompatibility. 1) Run Windows Memory Diagnostic: `mdsched.exe`. 2) Analyze minidumps located in `C:\\Windows\\Minidump` using WinDbg. 3) Update chipset and graphics drivers. 4) Use `sfc /scannow` to fix Windows corruption.",
        "tags": ["bsod", "hardware", "ram", "memory", "driver", "crash"],
        "related": ["KB-010"]
    },
    {
        "id": "KB-010",
        "title": "Hard Drive SMART Failure / Imminent Failure",
        "category": "hardware",
        "content": "Disk reporting SMART threshold exceeded: 1) IMMEDIATELY back up the user's local files. Do not run defrag. 2) Run quick check: `wmic diskdrive get status`. 3) Identify faulty drive. 4) Procure replacement SSD/HDD. 5) Inform user of device swap. 6) Securely wipe failed drive if returning for warranty, if possible.",
        "tags": ["smart", "hdd", "ssd", "disk", "failure", "backup"],
        "related": ["KB-009"]
    },
    {
        "id": "KB-011",
        "title": "Printer Network Offline / Cannot Print",
        "category": "hardware",
        "content": "Network printer showing offline: 1) Ping the printer IP. 2) If ping fails, check printer physical connection/power. 3) Check Print Spooler service on client: `Restart-Service -Name Spooler`. 4) Verify correct printer port (Standard TCP/IP rather than WSD). 5) Clear stale jobs located in `C:\\Windows\\System32\\spool\\PRINTERS`.",
        "tags": ["printer", "offline", "spooler", "print", "tcp/ip"],
        "related": []
    },
    {
        "id": "KB-012",
        "title": "Monitor Not Detected / No Signal",
        "category": "hardware",
        "content": "External display no signal: 1) Check physical cable connections (HDMI/DP/USB-C). 2) Test with alternative cable. 3) Press `Win + P` and ensure it's not set to 'PC screen only'. 4) Update graphics drivers. 5) If using a docking station, power cycle the dock and update dock firmware. 6) Check monitor input source.",
        "tags": ["monitor", "display", "no-signal", "docking-station", "hdmi"],
        "related": []
    },
    {
        "id": "KB-013",
        "title": "Laptop Battery Degradation / Not Charging",
        "category": "hardware",
        "content": "Laptop plugged in but not charging: 1) Run battery report: `powercfg /batteryreport`. 2) If full charge capacity is <50% of design capacity, replace battery. 3) Check AC adapter wattage (system might be throttling on low-watt charger). 4) Reset BIOS to defaults. 5) Run hardware diagnostics from BIOS screen.",
        "tags": ["battery", "laptop", "charging", "powercfg"],
        "related": []
    },
    {
        "id": "KB-014",
        "title": "Docking Station USB/Ethernet Not Working",
        "category": "hardware",
        "content": "Docking functionality impaired: 1) Verify required Thunderbolt software is running and device is 'Approved'. 2) Install latest DisplayLink drivers if applicable. 3) Hard reset the dock (unplug AC power for 30s). 4) Check Device Manager for hidden/failed hubs (`devmgmt.msc`). 5) Flash latest dock firmware via manufacturer utility.",
        "tags": ["dock", "docking-station", "thunderbolt", "usb", "ethernet"],
        "related": ["KB-012"]
    },
    {
        "id": "KB-015",
        "title": "BitLocker Recovery Key Prompt on Every Boot",
        "category": "hardware",
        "content": "System asking for BitLocker key on boot: 1) Usually caused by firmware update, hardware change, or PCR validation failure. 2) Provide user with Recovery Key from Intune/AD. 3) Once logged in, suspend and resume BitLocker to reset TPM bindings: `Manage-bde -protectors -disable c:` then `Manage-bde -protectors -enable c:`. 4) Ensure BIOS is updated.",
        "tags": ["bitlocker", "encryption", "tpm", "recovery-key", "boot"],
        "related": []
    },
    {
        "id": "KB-016",
        "title": "Active Directory Account Lockout Workflow",
        "category": "access",
        "content": "User account is locked out: 1) Search AD for the user: `Get-ADUser -Identity <username> -Properties LockedOut`. 2) Unlock the account: `Unlock-ADAccount -Identity <username>`. 3) To investigate the source of the lockout (stale credentials on mobile device or service account), check domain controller Security logs (Event ID 4740). 4) Force directory sync if hybrid AAD.",
        "tags": ["activedirectory", "ad", "lockout", "unlock", "event4740", "login"],
        "related": ["KB-017"]
    },
    {
        "id": "KB-017",
        "title": "MFA / Authenticator App Reset",
        "category": "access",
        "content": "User lost phone or needs MFA reset: 1) Verify user identity via video call or manager approval. 2) In Azure AD/Entra ID: Navigate to Users > Authentication methods > Require re-register MFA. 3) Revoke existing MFA sessions. 4) Provide user with temporary access pass (TAP) if configuring new device is delayed. 5) Send enrollment guide.",
        "tags": ["mfa", "authenticator", "azuread", "entra", "reset", "2fa"],
        "related": ["KB-016"]
    },
    {
        "id": "KB-018",
        "title": "Salesforce SSO Login Failure",
        "category": "access",
        "content": "Salesforce SAML SSO fails: 1) Check Azure AD/Okta enterprise applications sign-in logs for conditional access block. 2) Verify user is assigned to the Salesforce app. 3) Validate SAML assertions: verify NameID matches Salesforce Federation ID. 4) If certificate expired, update IdP certificate in Salesforce Single Sign-On Settings.",
        "tags": ["salesforce", "sso", "saml", "login", "okta", "azuread"],
        "related": []
    },
    {
        "id": "KB-019",
        "title": "File Server / Share Access Denied",
        "category": "access",
        "content": "Access Denied to \\\\corp-fs\\share: 1) Check effective permissions in Advanced Security Settings. 2) Determine which security group grants access. 3) Verify if user is in the group: `Get-ADGroupMember -Identity \"GroupName\"`. 4) Note: User must log out and log back in (or run `klist purge`) to receive an updated Kerberos ticket with the new group membership.",
        "tags": ["fileserver", "smb", "share", "permissions", "access-denied", "ad"],
        "related": []
    },
    {
        "id": "KB-020",
        "title": "Azure Role / AWS IAM Permission Denied",
        "category": "access",
        "content": "Cloud console access denied: 1) Check the exact error for missing action (e.g., `s3:GetObject`). 2) Review the IAM policies attached to the user/role. 3) Look for explicitly Deny statements in SCPs or permission boundaries. 4) If assuming a role, ensure trust relationship allows the user's identity. 5) Request access via standard approvals.",
        "tags": ["aws", "azure", "iam", "cloud", "permissions", "rbac"],
        "related": []
    },
    {
        "id": "KB-021",
        "title": "Local Admin Rights Request (LAPS)",
        "category": "access",
        "content": "User temporarily needs local admin: 1) Obtain manager approval and business justification. 2) Retrieve local admin password from LAPS UI or PowerShell: `Get-LapsADPassword -Identity <ComputerName>`. 3) Provide the credentials to the user. 4) Set the password to automatically expire/rotate after 4 hours to enforce least privilege.",
        "tags": ["laps", "admin", "privilege", "localadmin"],
        "related": []
    },
    {
        "id": "KB-022",
        "title": "Database Connection Refused (PostgreSQL/MySQL)",
        "category": "software",
        "content": "Cannot connect to database: 1) Verify the DB daemon is running: `systemctl status postgresql`. 2) Check if port 5432/3306 is listening: `netstat -tuln | grep 5432`. 3) Ensure `pg_hba.conf` allows the client IP. 4) Check for firewall rules on the DB server: `iptables -L` or Security Groups. 5) Verify credentials and max connection limits.",
        "tags": ["database", "postgresql", "mysql", "connection-refused", "sql"],
        "related": []
    },
    {
        "id": "KB-023",
        "title": "Java Heap Space / OutOfMemoryError",
        "category": "software",
        "content": "Application crashes with OOM: 1) Application is trying to allocate more memory than JVM allows. 2) Increase heap size in config: `-Xms2G -Xmx4G`. 3) If heap is already large, application might have a memory leak. 4) Generate a heap dump on OOM: `-XX:+HeapDumpOnOutOfMemoryError`. 5) Analyze the `.hprof` file with Eclipse MAT or similar tool.",
        "tags": ["java", "jvm", "oom", "memory_leak", "heap"],
        "related": []
    },
    {
        "id": "KB-024",
        "title": "Docker Container Unhealthy / Exited",
        "category": "software",
        "content": "Docker container failing: 1) Check container status: `docker ps -a`. 2) View logs: `docker logs <container_id>`. 3) If Exit Code 137, container was killed via SIGKILL (often OOM by kernel). Check `dmesg -T | grep -i oom`. 4) Verify volume mounts and environment variables. 5) Restart container or rebuild image: `docker compose up -d --force-recreate`.",
        "tags": ["docker", "container", "exit", "oom", "compose"],
        "related": []
    },
    {
        "id": "KB-025",
        "title": "Excel Crashing / Sluggish Performance",
        "category": "software",
        "content": "Excel is freezing: 1) Large datasets or too many formulas. Switch to Manual Calculation: Formulas > Calculation Options. 2) Disable hardware graphics acceleration: File > Options > Advanced. 3) Start Excel in Safe Mode: `excel.exe /safe`. If it works, an add-in is the culprit. Disable COM Add-ins. 4) Run Office Quick Repair.",
        "tags": ["excel", "office", "crash", "performance", "add-in", "safe-mode"],
        "related": []
    },
    {
        "id": "KB-026",
        "title": "Outlook Profile Corruption / Not Syncing",
        "category": "software",
        "content": "Outlook not updating folders: 1) Look at bottom status bar for 'Disconnected'. 2) Rebuild OST file: Close Outlook, navigate to `%localappdata%\\Microsoft\\Outlook`, rename the `.ost` file to `.old`, and restart Outlook. 3) Create a new Outlook profile via Control Panel > Mail. 4) Verify autodiscover records for the domain.",
        "tags": ["outlook", "email", "sync", "ost", "profile"],
        "related": []
    },
    {
        "id": "KB-027",
        "title": "Zoom Audio / Video Not Working",
        "category": "software",
        "content": "Zoom A/V failure: 1) Verify correct microphone/speaker selected in Zoom audio settings. 2) Check Windows privacy settings: Settings > Privacy > Microphone -> Allow apps to access. 3) Test audio in Windows Sound Control Panel. 4) Reinstall Zoom client. 5) Update audio/webcam drivers. Ensure no other app (e.g., Teams) is locking the camera device.",
        "tags": ["zoom", "audio", "video", "microphone", "webcam"],
        "related": []
    },
    {
        "id": "KB-028",
        "title": "Git Merge Conflict / Detached HEAD",
        "category": "software",
        "content": "Developer stuck in Git: 1) Detached HEAD: `git checkout main` to return to a branch. 2) Abandon a merge conflict: `git merge --abort`. 3) Resolving conflicts: open files, fix the `<<<<<<<` markers, run `git add <file>`, then `git commit`. 4) If committed to wrong branch, `git reset --soft HEAD~1`. Advise user to use a visual merge tool.",
        "tags": ["git", "developer", "merge", "conflict", "detached-head"],
        "related": []
    },
    {
        "id": "KB-029",
        "title": "Phishing Email Reported by User",
        "category": "security",
        "content": "User reports phishing: 1) Instruct the user DO NOT click links and DO NOT forward the email natively (use 'Forward as Attachment'). 2) Analyze headers in Security Center. 3) Purge the email from all mailboxes using Office 365 Threat Explorer or PowerShell `Search-Mailbox -DeleteContent`. 4) Reset user password if they clicked the link and entered credentials. 5) Block sender IP/Domain.",
        "tags": ["phishing", "email", "security", "compromise", "purge"],
        "related": ["KB-030"]
    },
    {
        "id": "KB-030",
        "title": "Account Compromise / Suspicious Login",
        "category": "security",
        "content": "Unusual sign-in detected (e.g., impossible travel): 1) Assume compromise. Immediately disable the AD/Entra account. 2) Revoke all active sessions (Azure AD -> Revoke Sessions). 3) Force password reset on next login. 4) Review mailbox inbox rules for forwarding rules created by attacker to hide activity. 5) Check sign-in logs for IPs to block in Conditional Access.",
        "tags": ["compromise", "breach", "impossible-travel", "login", "security"],
        "related": ["KB-016", "KB-029"]
    },
    {
        "id": "KB-031",
        "title": "Malware / Ransomware Detected by EDR (CrowdStrike/Defender)",
        "category": "security",
        "content": "Endpoint Detection & Response flagged malware: 1) EDR usually auto-contains, but verify containment status in console. 2) If not contained, network isolate the host immediately. 3) DO NOT turn off the machine; preserve RAM for forensics. 4) Escalate to SOC/Incident Response team. 5) Pull process tree and identify the parent execution (e.g., malicious macro).",
        "tags": ["malware", "ransomware", "edr", "crowdstrike", "defender", "isolation"],
        "related": []
    },
    {
        "id": "KB-032",
        "title": "Lost or Stolen Device",
        "category": "security",
        "content": "User device missing: 1) Verify if device has BitLocker/FDE active. 2) Issue Remote Wipe command via Intune or MDM immediately. 3) Disable user's VPN certificates and ActiveSync connections. 4) File a hardware loss incident ticket. 5) If unencrypted, force reset all passwords for that user and review access logs for data exfiltration.",
        "tags": ["lost", "stolen", "mdm", "wipe", "intune", "bitlocker"],
        "related": []
    },
    {
        "id": "KB-033",
        "title": "Suspicious USB Drive Activity",
        "category": "security",
        "content": "Unauthorized USB mass storage detected: 1) Corporate policy usually blocks USBs via GPO/EDR. 2) Check EDR logs for file copy events or execution from `D:\\` or `E:\\`. 3) Contact user to determine origin of the USB (Drop-baiting attack?). 4) If malicious execution suspected, isolate the host. 5) Format USB if confiscated and safe to do so.",
        "tags": ["usb", "storage", "dlp", "security"],
        "related": []
    },
    {
        "id": "KB-034",
        "title": "Data Loss Prevention (DLP) Policy Violation",
        "category": "security",
        "content": "DLP triggered (e.g., SSN/Credit Card emailed or uploaded): 1) Review the DLP alert in Purview/Security center. 2) Check the confidence level and determine if it's a false positive. 3) If true positive, block the transaction/email. 4) Contact the user and their manager to reinforce data handling policy. 5) Verify if external recipient received the data; if so, initiate legal/compliance disclosure.",
        "tags": ["dlp", "data-loss", "ssn", "compliance", "purview"],
        "related": []
    },
    {
        "id": "KB-035",
        "title": "Exchange Server Mailflow Stopped",
        "category": "software",
        "content": "No emails coming in or out: 1) Check disk space on Exchange server (backpressure stops mail delivery if drive has <10% free space). 2) Verify Microsoft Exchange Transport service is running: `Restart-Service MSExchangeTransport`. 3) Test SMTP manually using telnet to port 25. 4) Check edge gateway/spam filter configuration and connection.",
        "tags": ["exchange", "mailflow", "smtp", "backpressure", "transport"],
        "related": []
    },
    {
        "id": "KB-036",
        "title": "Active Directory Replication Issues",
        "category": "network",
        "content": "Changes (passwords/groups) not syncing: 1) Force AD replication: `repadmin /syncall /A /d /e`. 2) Check replication summary for errors: `repadmin /showrepl`. 3) Typical issues: DNS misconfiguration, time synchronization skew (>5 minutes breaks Kerberos), or RPC port (135/high ports) blocked between Domain Controllers.",
        "tags": ["ad", "activedirectory", "replication", "repadmin", "sync"],
        "related": []
    },
    {
        "id": "KB-037",
        "title": "Time Sync / NTP Drift (Kerberos Failures)",
        "category": "network",
        "content": "Time is wrong, causing login issues: 1) Kerberos requires max 5 min time skew. 2) Re-sync time with domain controller: `w32tm /resync`. 3) Check NTP source on PDC emulator: `w32tm /query /source`. 4) If PDC is wrong, point it to external time servers: `w32tm /config /manualpeerlist:pool.ntp.org /syncfromflags:manual /reliable:yes /update`.",
        "tags": ["ntp", "time", "clock", "w32tm", "kerberos", "skew"],
        "related": ["KB-036"]
    },
    {
        "id": "KB-038",
        "title": "Virtual Machine Unresponsive in VMware/Hyper-V",
        "category": "hardware",
        "content": "VM hung/frozen: 1) Look at hypervisor console performance metrics (CPU ready time, ballooning). 2) Try Soft Reset/Guest OS restart via VMware Tools. 3) If tools unresponsive, issue Hard Reset. 4) Check datastore latency (storage issue). 5) If VM is orphaned, unregister and re-register in vCenter.",
        "tags": ["vm", "vmware", "hyper-v", "frozen", "unresponsive", "vcenter"],
        "related": []
    },
    {
        "id": "KB-039",
        "title": "Teams Client Stuck in Login Loop / Cache Clear",
        "category": "software",
        "content": "MS Teams keeps restarting: 1) Quit Teams completely. 2) Delete Teams cache: `rmdir /q /s %appdata%\\Microsoft\\Teams` (For New Teams: Repair/Reset app in Settings). 3) Re-launch Teams and sign in. 4) Check for conflicting credential manager entries in Windows Control Panel. 5) Reinstall Teams via MSI/EXE.",
        "tags": ["teams", "loop", "cache", "login", "microsoft"],
        "related": []
    },
    {
        "id": "KB-040",
        "title": "Slack Connectivity Issues",
        "category": "software",
        "content": "Slack unable to connect to websocket: 1) Check Slack status page (status.slack.com). 2) Clear cache: Help > Troubleshooting > Clear Cache and Restart. 3) Ensure firewall allows WSS (WebSocket over SSL) to `wss://*.slack-msgs.com`. 4) Reset App Data. 5) Verify local time synchronization.",
        "tags": ["slack", "websocket", "connection", "cache"],
        "related": []
    },
    {
        "id": "KB-041",
        "title": "macOS / Mac Intune Enrollment Error",
        "category": "software",
        "content": "Mac failing to enroll in MDM: 1) Verify existing profiles are removed: System Settings > Privacy & Security > Profiles. 2) Device might still be tied to Apple Business Manager for another organization. 3) Download latest Company Portal. 4) Check logs in `/var/log/install.log` for MDM payload failures. 5) Run `sudo profiles renew -type enrollment`.",
        "tags": ["mac", "macos", "intune", "mdm", "enrollment", "profile"],
        "related": []
    },
    {
        "id": "KB-042",
        "title": "Chrome / Edge Browser Out of Memory",
        "category": "software",
        "content": "Browser showing 'Aw, Snap!' / Out of Memory: 1) Disable aggressive extensions (e.g., heavy ad-blockers, grammar checkers). 2) Clear site data and cookies. 3) Enable memory saver mode in browser settings. 4) Check Windows pagefile size. 5) Use Chrome Task Manager (`Shift + Esc`) to identify the tab consuming gigabytes of RAM.",
        "tags": ["chrome", "edge", "browser", "oom", "memory", "tab"],
        "related": []
    },
    {
        "id": "KB-043",
        "title": "Restoring Deleted Files (SharePoint / OneDrive)",
        "category": "software",
        "content": "User deleted an important file: 1) Check the First-Stage Recycle Bin in SharePoint/OneDrive site. 2) If deleted from there, check the Second-Stage (Site Collection) Recycle Bin. Data is kept for 93 days. 3) If past 93 days, initiate a restore from the backup appliance (e.g., Veeam, Datto, Rubrik).",
        "tags": ["restore", "deleted", "file", "sharepoint", "onedrive", "backup", "recycle-bin"],
        "related": []
    },
    {
        "id": "KB-044",
        "title": "SSL/TLS Certificate Expiry Mitigation",
        "category": "security",
        "content": "Service offline because of expired SSL: 1) Verify expiration date (`openssl s_client -connect mydomain.com:443 -servername mydomain.com`). 2) Generate new CSR and submit to CA. 3) Issue temporary self-signed cert or Let's Encrypt while waiting. 4) Install new cert and restart web service (e.g., `systemctl restart nginx`). 5) Update cert in load balancer.",
        "tags": ["ssl", "tls", "certificate", "expired", "https"],
        "related": []
    },
    {
        "id": "KB-045",
        "title": "Kubernetes Pod in CrashLoopBackOff",
        "category": "software",
        "content": "K8s pod failing continuously: 1) Check pod status: `kubectl get pods`. 2) View logs of the crashing container: `kubectl logs <pod-name> --previous`. 3) Describe pod to see events (OOMKilled, Liveness probe failed): `kubectl describe pod <pod-name>`. 4) Check ConfigMap or Secret changes that might crash the app. 5) Temporarily override command to `/bin/sh` to investigate.",
        "tags": ["kubernetes", "k8s", "pod", "crashloopbackoff", "kubectl"],
        "related": []
    },
    {
        "id": "KB-046",
        "title": "Linux Server Unreachable via SSH",
        "category": "network",
        "content": "Cannot SSH to Linux VM: 1) Check ICMP (ping). 2) Use virtualization console to log in interactively. 3) Verify sshd is running: `systemctl status sshd`. 4) Check for firewall rules (`ufw status` or `iptables-save`). 5) Check for IP routing issues. 6) Verify SSH key permissions: `~/.ssh/authorized_keys` must be 600 or 644.",
        "tags": ["ssh", "linux", "unreachable", "sshd", "connection"],
        "related": []
    },
    {
        "id": "KB-047",
        "title": "Windows User Profile Service Failed the Logon",
        "category": "software",
        "content": "Login fails with 'User Profile Service failed': 1) The registry key of the profile is corrupted. 2) Log in with a local admin account. 3) Open `regedit` and go to `HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\ProfileList`. 4) Find the SID with `.bak` at the end. Delete the profile folder in `C:\\Users`, delete the SID key without `.bak`, and rename the `.bak` key.",
        "tags": ["windows", "profile", "logon", "registry", "corrupted"],
        "related": []
    },
    {
        "id": "KB-048",
        "title": "IP Phone / VoIP Not Registering",
        "category": "network",
        "content": "Desk phone shows No Service/Unregistered: 1) Verify voice VLAN assignment on the switch port (e.g., `switchport voice vlan 10`). 2) Ensure DHCP Option 150 (TFTP server for CUCM) or Option 66 is set. 3) Verify MAC address matches Cisco/Avaya PBX profile. 4) Reboot the phone. 5) Check for SIP ALG interference on firewall if remote phone.",
        "tags": ["voip", "sip", "phone", "unregistered", "tftp", "vlan"],
        "related": []
    },
    {
        "id": "KB-049",
        "title": "Employee Offboarding Process (Immediate Termination)",
        "category": "access",
        "content": "Hostile termination offboarding: 1) Immediately reset AD password and scramble it. 2) Disable AD account. 3) Revoke OAuth tokens/sessions in Azure AD. 4) Block sign-in in O365. 5) Convert mailbox to Shared Mailbox and grant manager access. 6) Issue device wipe command to phone/laptop via MDM. 7) Inform facilities to disable physical badge access.",
        "tags": ["offboarding", "termination", "hr", "disable", "wipe"],
        "related": ["KB-016"]
    },
    {
        "id": "KB-050",
        "title": "Adding Mailbox Delegation (Full Access / Send As)",
        "category": "access",
        "content": "Granting an assistant access to a manager's mailbox: 1) Exchange Admin Center: Mailboxes -> Manager -> Delegation. 2) Add user to Full Access. 3) Add user to Send As (requires AD sync if hybrid). 4) Or via PowerShell: `Add-MailboxPermission -Identity manager@domain.com -User assistant@domain.com -AccessRights FullAccess -AutoMapping $true`.",
        "tags": ["exchange", "mailbox", "delegation", "full-access", "send-as"],
        "related": []
    },
    {
        "id": "KB-051",
        "title": "AWS S3 Bucket Access Denied (Cross-Account)",
        "category": "access",
        "content": "Unable to read S3 bucket from another AWS account: 1) Source account must have IAM identity policy allowing `s3:GetObject`. 2) Destination account bucket MUST have a Bucket Policy explicitly trusting the source account ID. 3) Ensure KMS key policy allows decryption by the source account. 4) Disable Block Public Access if intentionally sharing (careful).",
        "tags": ["aws", "s3", "iam", "cross-account", "bucket-policy", "kms"],
        "related": ["KB-020"]
    },
    {
        "id": "KB-052",
        "title": "Terraform State Lock Issue",
        "category": "software",
        "content": "Terraform fails with 'Error acquiring the state lock': 1) Ensure no one else is actively running `terraform apply`. 2) Identify the Lock ID from the output. 3) If CI pipeline crashed, force unlock the state file: `terraform force-unlock <LOCK_ID>`. 4) Note: Doing this while someone is actually running apply can corrupt the state.",
        "tags": ["terraform", "state", "lock", "devops", "unlock"],
        "related": []
    },
    {
        "id": "KB-053",
        "title": "Clear browser cache and cookies unconditionally",
        "category": "software",
        "content": "To clear all cache/cookies: In Chrome press Ctrl+Shift+Del -> Advanced -> All Time -> Select Cookies, Cache -> Clear data. Alternatively open DevTools (F12) -> Application tab -> Storage -> Clear Site Data. Reopen browser.",
        "tags": ["browser", "chrome", "cache", "cookies", "clear"],
        "related": ["KB-042"]
    },
    {
        "id": "KB-054",
        "title": "No space left on device (Linux)",
        "category": "software",
        "content": "Disk full: 1) Check partitions with `df -h`. 2) Find large directories: `du -ah / | sort -rh | head -n 20`. 3) Clear apt cache: `apt-get clean`. 4) Clear log files: `journalctl --vacuum-time=3d` or truncate files: `truncate -s 0 /var/log/syslog`. 5) Check if deleted files are still held by processes using `lsof | grep deleted`.",
        "tags": ["linux", "disk", "full", "space", "df", "du"],
        "related": []
    },
    {
        "id": "KB-055",
        "title": "Windows Update Stuck / Failing",
        "category": "software",
        "content": "Windows Update stuck at 0%: 1) Stop Windows Update service: `net stop wuauserv`. 2) Stop BITS: `net stop bits`. 3) Delete the SoftwareDistribution folder: `Remove-Item -Path \"C:\\Windows\\SoftwareDistribution\" -Recurse -Force`. 4) Restart services: `net start wuauserv` & `net start bits`. 5) Click Check for updates again.",
        "tags": ["windows", "update", "stuck", "softwaredistribution", "wus"],
        "related": []
    }
]


class MockKnowledgeBase:
    """
    RAG Simulation: Mock Knowledge Base with TF-IDF search.
    Agents can search for string, and pay SLA time to read.
    """

    def __init__(self):
        self.articles = KB_ARTICLES
        self.doc_freq = collections.defaultdict(int)
        self.total_docs = len(self.articles)
        self.search_cost_minutes = 2
        self._build_index()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"\w+", text.lower())

    def _build_index(self):
        """Build term frequency and document frequency index."""
        self.tf_index = []
        for doc in self.articles:
            # boost title and tags
            text = doc["title"] + " " + doc["title"] + " " + doc["content"] + " " + " ".join(doc["tags"]) * 3
            tokens = self._tokenize(text)
            tf = collections.Counter(tokens)
            self.tf_index.append(tf)

            for term in set(tokens):
                self.doc_freq[term] += 1
        logger.info(f"Knowledge base initialized with {self.total_docs} articles")

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        return math.log(self.total_docs / (1 + df))

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Production-grade KB search with better scoring"""
        if not query or not query.strip():
            return []

        query_tokens = self._tokenize(query)
        scores = []

        for i, article in enumerate(self.articles):
            tfidf = self.tf_index[i]
            score = sum(tfidf.get(token, 0.0) for token in query_tokens)

            # Boost for title match and category match
            if query.lower() in article["title"].lower():
                score += 2.0
            if article["category"] in query.lower():
                score += 1.0

            # Tag boost
            tag_hits = sum(1 for t in query_tokens if t in article.get("tags", []))
            score += tag_hits * 0.8

            if score > 0:
                scores.append((score, i))

        scores.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, idx in scores[:top_k]:
            article = self.articles[idx]
            results.append({
                "id": article["id"],
                "title": article["title"],
                "category": article["category"],
                "content_snippet": article["content"][:280] + "..." if len(article["content"]) > 280 else article["content"],
                "relevance_score": round(min(score / 8.0, 0.99), 4),
                "tags": article.get("tags", []),
            })

        return results

    def get_search_cost(self) -> int:
        return self.search_cost_minutes

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_articles": self.total_docs,
            "cost_per_search": self.search_cost_minutes,
            "categories": list(set(d["category"] for d in self.articles))
        }
