# Hermes/OpenClaw to qclaw Migration Principles
Source: HERMES-OPENCLAW-MIGRATION.md + .opencode.md

## Core Principle

Source systems (Hermes/OpenClaw/Claude Code) are INPUTS, not final runtimes.
qclaw is the final runtime. Only preserve reusable behaviors.

## 5-Layer Translation Map

### 1. Scheduler / Cron
Source: cron/scheduler.py, recurring loops
-> qclaw: qclaw-cron-skill (exists), ECC hook

### 2. Gateway / Dispatch
Source: Hermes gateway, session routing
-> qclaw: session adapter + control-plane

### 3. Memory
Source: memory_tool.py, local operator memory
-> qclaw: knowledge-ops, WORKING-CONTEXT.md, KB-backed context
Key: repo context near repo, cross-repo memory in KB/archive

### 4. Skill Layer
Source: Hermes skills, OpenClaw skills
-> qclaw native skill: when workflow is reusable
-> hooks/commands: when behavior is procedural
Already migrated: knowledge-ops, github-ops, hookify-rules

### 5. Tool / Service
Source: custom service wrappers
-> qclaw: MCP-backed surfaces (when connector exists)
-> qclaw: operator skills (when workflow logic is real asset)

## OpenCode vs Claude Code Hooks

| Claude Code | OpenCode Plugin | Notes |
| PreToolUse | tool.execute.before | Can modify input |
| PostToolUse | tool.execute.after | Can modify output |
| Stop | session.idle | Session lifecycle |
| SessionStart | session.created | Session starts |
| N/A | file.edited | OpenCode-only |
| N/A | lsp.client.diagnostics | OpenCode-only |
| N/A | tui.toast.show | OpenCode-only |

## What NOT to Import

- secrets
- personal datasets
- account tokens
- local-only business artifacts

## Key Insight

The public repo should describe the adapter boundary and control-plane model, not rebuild a shadow private workspace.
