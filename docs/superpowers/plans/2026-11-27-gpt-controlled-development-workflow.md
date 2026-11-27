# GPT-Controlled Development Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add durable, repository-specific instructions and review procedures so ChatGPT can safely manage future video-editor development from GitHub without relying on local development tools or pretending independent agents exist.

**Architecture:** Keep the workflow documentation-only and place it on `video-editor-lab`. The approved design is recorded as the specification; root-level instructions establish persistent project constraints, while focused workflow and review documents define the operating procedure. No application code, CI configuration, dependencies, deployment configuration, or Stage 2 feature work is changed.

**Tech Stack:** GitHub repository contents API; Markdown documentation; existing Superpowers skills; Context7 documentation lookup; existing GitHub Actions workflow as an already-established verification source.

**Spec:** `docs/superpowers/specs/2026-11-27-gpt-controlled-development-workflow-design.md`

## Global Constraints

- Repository: `promiseoluo66-cmyk/northgate-realty-demo` only.
- Target branch: `video-editor-lab` only; never modify `main`.
- Do not use `sparkle-clean-co` or move this project to another repository.
- Treat the Sparkle Clean repository's GitHub Actions allowance as exhausted for this month; do not trigger workflows there.
- Do not trigger unnecessary GitHub Actions runs; this documentation-only work must not change workflow files or application paths.
- Do not begin Stage 2 Task 2.4 or any other video-editor feature implementation.
- Do not add dependencies, paid services, billing requirements, secrets, tokens, or credentials.
- Do not merge, deploy, publish a release, send messages, or perform other irreversible external actions without explicit approval.
- Use GitHub-connected repository tools; do not require a PC, terminal, VS Code, Codespaces, or local commands from the user.
- Describe specialist roles as reviews performed by the same ChatGPT session unless a genuine independent-agent runtime becomes available.
- Preserve existing working features, project decisions, and the existing GitHub Actions workflow.
- Treat existing CI results as historical evidence; never claim a fresh test run without a fresh result.

## Review Focus

- Wrong repository or branch selected — verify repository identity and branch before every write; verify all changed files remain on `video-editor-lab`.
- Existing project instructions or docs accidentally overwritten — fetch each target path first; update only when required and preserve existing content.
- Agent capabilities overstated — explicitly distinguish role-based reviews from independent agents and do not claim delegation.
- Workflow documentation accidentally authorises Stage 2 Task 2.4 — test the written constraints by searching every new document for Task 2.4 references and confirming it is explicitly excluded.
- Documentation changes unexpectedly trigger CI or alter application behavior — keep all new files outside `video-editor/**` and `.github/workflows/**`; inspect the final changed-file list.

---

### Task 1: Record the approved design specification

**Files:**
- Create: `docs/superpowers/specs/2026-11-27-gpt-controlled-development-workflow-design.md`

**Interfaces:**
- Consumes: the user-approved configuration design from this conversation.
- Produces: the authoritative design document referenced by this plan.

- [ ] **Step 1: Confirm target branch and file absence** using GitHub repository/branch reads and fetch the exact target path on `video-editor-lab`.
- [ ] **Step 2: Create the design document** with the approved objective, repository boundaries, workflow stages, specialist-review limitation, security/cost controls, exclusions, and acceptance criteria. Do not add new architectural decisions.
- [ ] **Step 3: Read the created file back** from `video-editor-lab` and compare it with the approved design.
- [ ] **Step 4: Verify the commit** belongs to `video-editor-lab` and contains only the intended specification file.

### Task 2: Add the repository operating procedure

**Files:**
- Create: `docs/superpowers/WORKFLOW.md`

**Interfaces:**
- Consumes: the approved design specification from Task 1.
- Produces: the repeatable end-to-end procedure used for future project work.

- [ ] **Step 1: Define the workflow stages**: repository/status inspection; brainstorming and design approval; implementation planning and plan approval; current documentation research with Context7; test-first implementation; systematic debugging; specialist reviews; final verification and evidence-based reporting.
- [ ] **Step 2: Define GitHub-only execution rules**: inspect before writes, use exact repository and branch, read files before updates, make small reviewable commits, and verify every write by reading it back.
- [ ] **Step 3: Define approval gates** for code changes, workflow changes, merges, deployments, releases, and other external/irreversible actions.
- [ ] **Step 4: Define test and evidence reporting**: distinguish existing CI evidence from fresh runs; report exact run/commit, passed and failed tests, skipped checks, and blockers; do not claim unverified success.
- [ ] **Step 5: Verify the procedure** against the approved specification and ensure no step authorises Stage 2 Task 2.4.

### Task 3: Add specialist review checklist

**Files:**
- Create: `docs/superpowers/REVIEW_CHECKLIST.md`

**Interfaces:**
- Consumes: the workflow and approved design.
- Produces: bounded review checklists for architecture, research, implementation, debugging, testing, security, and final QA.

- [ ] **Step 1: Define each review role's responsibility and review questions** without representing these roles as independent agents.
- [ ] **Step 2: Add cross-cutting checks** for regressions, branch/repository scope, secrets, cost, accessibility/usability where relevant, and test evidence.
- [ ] **Step 3: Add a findings format** with severity, affected path, evidence, required correction, and verification result.
- [ ] **Step 4: Verify the checklist** contains no unsupported tool claims and does not duplicate the operating procedure unnecessarily.

### Task 4: Add persistent repository instructions

**Files:**
- Create: `AGENTS.md`

**Interfaces:**
- Consumes: the approved specification, workflow, and review checklist.
- Produces: concise root-level instructions discoverable by AI coding assistants.

- [ ] **Step 1: Fetch the root `AGENTS.md` path** on `video-editor-lab`; if it already exists, preserve and carefully extend it rather than replacing it blindly.
- [ ] **Step 2: Add only durable project rules**: repository/branch boundaries, phone/GitHub-only execution, $0/no-billing constraint, approval gates, preservation requirements, testing/evidence standards, and links to the detailed workflow documents.
- [ ] **Step 3: State explicitly** that no native independent-agent runtime is currently available and role-based reviews must not be described as separate agents.
- [ ] **Step 4: Read the final file back** and verify it is concise, non-contradictory, and consistent with existing project instructions.

### Task 5: Final documentation and repository-scope verification

**Files:**
- Verify: all files created in Tasks 1–4.
- Verify: no application source, tests, CI workflow, migrations, or deployment files changed.

**Interfaces:**
- Consumes: the four completed documentation files.
- Produces: verified documentation set and a concise evidence report.

- [ ] **Step 1: Fetch all four files from `video-editor-lab`** and verify their contents.
- [ ] **Step 2: Inspect the branch commit/diff** and confirm only the four intended documentation paths changed.
- [ ] **Step 3: Check consistency** across the design, workflow, checklist, and `AGENTS.md`; verify all links and paths match.
- [ ] **Step 4: Check exclusions**: no Stage 2 Task 2.4 implementation; no changes to `video-editor/**`, `.github/workflows/**`, `main`, Sparkle Clean, deployment settings, or secrets.
- [ ] **Step 5: Report verification honestly**. Since this is documentation-only and the existing workflow is not being changed, do not trigger CI merely to validate Markdown. Report repository read-back and diff evidence; state clearly that no fresh CI run was performed.

## Completion Criteria

- The approved specification, operating procedure, specialist checklist, and root instructions exist on `video-editor-lab`.
- Every document reflects the user's repository, cost, device, security, and approval constraints.
- No claim is made that separate AI agents were launched.
- Only the intended documentation paths changed.
- No Stage 2 feature work, CI workflow change, merge, deployment, or release occurred.
