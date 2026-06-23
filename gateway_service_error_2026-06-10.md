# Gateway Service Error - 2026-06-10

## Objective
Diagnose and resolve OpenClaw gateway service startup failure.

## Issue Description
- **Status**: Gateway runtime is stopped
- **Error**: "The system cannot find the file specified."
- **Service State**: Service unit not found (not installed)
- **Connectivity**: Probe target ws://127.0.0.1:7687 is reachable
- **Capability**: Admin-capable

## Root Cause Analysis
The gateway service is not properly installed as a Windows service. The error indicates either:
1. The service executable is missing or corrupted
2. The service registration is incomplete
3. File permissions issue preventing access to required files

## Recommended Actions
1. **Install the gateway service**:
   ```powershell
   openclaw gateway install
   ```

2. **Start the gateway**:
   ```powershell
   openclaw gateway start
   ```

3. **Verify installation**:
   ```powershell
   openclaw gateway status
   ```

## Next Steps
- User needs to run `openclaw gateway install` to register the service
- If installation fails, check file permissions and antivirus interference
- Review logs at: `\tmp\openclaw\openclaw-2026-06-10.log`

## Technical Details
- **Config location**: `~\.qclaw\openclaw.json`
- **Log location**: `\tmp\openclaw\openclaw-2026-06-10.log`
- **Dashboard**: http://127.0.0.1:7687/
- **Bind address**: 127.0.0.1:7687 (loopback-only)

## Status
🟡 **PENDING USER ACTION** - Awaiting service installation command execution.
