# GPT-Controlled Development Workflow

This document defines how ChatGPT works on the video-editor project. The root `AGENTS.md` contains the short, persistent rules; the approved design is in `docs/superpowers/specs/2026-11-27-gpt-controlled-development-workflow-design.md`; specialist checks are in `docs/superpowers/REVIEW_CHECKLIST.md`.

## 1. Pre-flight inspection

Before changing anything:

1. Confirm the repository is `promiseoluo66-cmyk/northgate-realty-demo`.
2. Confirm the target branch is `video-editor-lab`; never write to `main`.
3. Read the current branch commit and inspect relevant files, existing instructions, project status, and recent decisions.
4. Identify completed work, unfinished work, known limitations, and existing tests.
5. Check whether a requested task overlaps existing functionality. Extend existing implementations rather than duplicating them.
6. Check cost and permission implications. No paid service, billing activation, or unnecessary CI run.

If repository or branch identity cannot be verified, stop before writing.

## 2. Design and approval gate

For substantial work, use the Superpowers brainstorming process:

1. Clarify the problem and constraints from existing project context.
2. Consider viable approaches and explain material trade-offs.
3. Present a design covering architecture, file boundaries, security, cost, failure handling, and acceptance criteria.
4. Wait for explicit approval of the design.
5. Only after approval, create the implementation plan.

Do not treat approval of a general direction as approval for unreviewed feature changes.

## 3. Planning and approval gate

Use Superpowers writing-plans. Plans must include:

- Exact repository paths to create or modify.
- Clear interfaces and dependencies between tasks.
- Small, independently verifiable steps.
- Test-first requirements for code changes.
- Expected outcomes for every verification step.
- Security, regression, and cost considerations.
- Explicit exclusions and approval gates.

Save plans under `docs/superpowers/plans/`. Ask the user to approve the plan before implementation unless they have already explicitly approved that exact plan and execution approach.

## 4. Research

Use Context7 when a task depends on library APIs, framework behavior, SDKs, or platform documentation that may have changed. Prefer official documentation and record relevant version/API assumptions.

Do not use research as a reason to replace established project decisions without presenting the trade-off and obtaining approval where required.

## 5. Implementation

- Work only through the connected GitHub tools on `video-editor-lab`.
- Read a file before updating it; preserve unrelated content.
- Make small, reviewable changes with clear commit messages.
- For code changes, follow Superpowers test-driven development: write the test first, observe the expected failure, implement the smallest change, and verify the test passes.
- Do not add dependencies or restructure unrelated components.
- Keep secrets out of commits and logs.
- Do not ask the user to use a PC, terminal, VS Code, or Codespaces.

Documentation-only work does not require inventing production-code tests. Verify documentation by reading every created or updated file back from GitHub, checking links and consistency, and inspecting the exact commit diff.

## 6. Debugging

When a test or operation fails:

1. Capture the exact error and the step that produced it.
2. Reproduce the failure where possible.
3. Trace the failure to its underlying cause.
4. Check relevant inputs, state, dependencies, and environment assumptions.
5. Apply the smallest justified correction.
6. Re-run the focused check and the appropriate broader test suite.
7. Report unresolved failures honestly.

Use the Superpowers systematic-debugging process. Do not hide failures or change tests merely to make them pass.

## 7. Specialist review

Review the work from these perspectives: architecture, research, implementation, debugging, testing, security, and final QA. These are review roles performed by the same ChatGPT session, not independent agents. No native independent-agent runtime is currently available.

Use `docs/superpowers/REVIEW_CHECKLIST.md`. Record findings with severity, affected path, evidence, correction, and verification.

## 8. GitHub Actions and verification

The existing Northgate workflow is the project's cloud verification path. Inspect its triggers and relevant run history before deciding whether a new run is necessary.

- Do not trigger Actions just to create activity or re-prove unrelated historical results.
- Do not use the Sparkle Clean repository; its Actions allowance is treated as exhausted for this month.
- Do not change workflow files as part of documentation configuration.
- A historical passing run is not a fresh test of new changes.
- If no fresh run is performed, say so clearly.
- Verify branch, commit, changed-file list, and file read-back through GitHub.

## 9. Permission gates

Obtain explicit user permission before:

- Merging a pull request or otherwise integrating changes into `main`.
- Deploying or publishing a release.
- Changing production infrastructure, secrets, billing, or paid services.
- Sending emails/messages or publishing content.
- Performing destructive or irreversible actions.
- Beginning Stage 2 Task 2.4. Until separately authorised, Stage 2 Task 2.4 must remain unstarted.

Never infer permission for these actions from approval of a design or implementation plan.

## 10. Completion report

Every completion report must state:

- Exact repository and branch.
- Exact files created or modified.
- Commit SHA and GitHub link.
- Tests/checks actually run and their observed results.
- Whether GitHub Actions ran; if not, say why.
- Review findings, deferred issues, and remaining blockers.
- Confirmation that protected branches, unrelated repositories, and excluded tasks were untouched.

Never claim completion beyond the evidence collected.
