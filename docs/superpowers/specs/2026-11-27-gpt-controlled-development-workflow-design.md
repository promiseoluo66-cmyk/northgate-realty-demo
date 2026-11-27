# GPT-Controlled Development Workflow — Design

**Status:** Approved by the project owner on 2026-11-27  
**Repository:** `promiseoluo66-cmyk/northgate-realty-demo`  
**Development branch:** `video-editor-lab`

## 1. Objective

Establish a safe, repeatable process for ChatGPT to manage the video-editor project through the connected GitHub repository tools, using Superpowers for disciplined development, Context7 for current technical documentation, and the existing GitHub Actions workflow for cloud verification where appropriate.

The user works from an Android phone and must not need a PC, terminal, VS Code, Codespaces, or a locally running process. The current budget is $0.

## 2. Approved architecture

- **ChatGPT:** primary development controller, implementer, debugger, and reviewer in this session.
- **GitHub:** source of truth for code, plans, documentation, branches, commits, and reviewable changes.
- **Superpowers:** process guidance for brainstorming, design approval, planning, test-driven development, systematic debugging, code review, and verification.
- **Context7:** current library and platform documentation lookup when implementation depends on external APIs or changing technical details.
- **GitHub Actions:** cloud test execution through the repository's existing workflow when a run is justified and authorised.
- **Android:** user review and approval interface only; no local build environment is required.

## 3. Repository and branch boundaries

All work for this video-editor project must use `promiseoluo66-cmyk/northgate-realty-demo` and the `video-editor-lab` branch.

The `main` branch contains the original Northgate Realty website and must remain untouched. The unrelated `sparkle-clean-co` repository must not be used, and this project must not be moved to another repository.

The existing Northgate video-editor CI history is evidence of prior verification, not proof that a new change has passed. Do not trigger unnecessary Actions runs. Treat the Sparkle Clean repository's Actions allowance as exhausted for the current month; do not run workflows there.

## 4. Development workflow

1. Inspect repository identity, branch, current commit, working project status, existing instructions, relevant files, and prior decisions before proposing changes.
2. For substantial work, brainstorm options and constraints, write a design, and obtain explicit user approval before planning implementation.
3. Write a detailed, small-step implementation plan with exact paths, interfaces, and verification criteria; obtain approval before implementation.
4. Use Context7 to check current official or authoritative documentation when external APIs, libraries, or platform behavior matter.
5. Implement in small, reviewable changes using test-driven development for code changes. Watch tests fail for the expected reason before implementing, then verify they pass.
6. Use systematic debugging when verification fails; diagnose the cause rather than patching symptoms.
7. Perform bounded specialist reviews for architecture, research, implementation, debugging, testing, security, and final QA.
8. Verify the exact GitHub diff, changed paths, commit, and relevant test evidence before reporting completion.

## 5. Agent capability truthfulness

The available environment does not currently expose a genuine independent AI-agent or subagent runtime. The named specialist responsibilities are therefore review perspectives performed by the same ChatGPT session. Do not describe them as separately launched agents, independent workers, or parallel AI agents.

If a genuine agent capability becomes available later, inspect its actual tool contract and permissions before using it. Do not create repository agent configuration files that have no verified consumer.

GitHub Actions is a CI runner, not an AI agent runtime. Parallel tool calls are not independent agents.

## 6. Security, cost, and approval controls

- Preserve existing working features and established project decisions.
- Keep credentials, tokens, and secrets out of source files, documentation, logs, and commits.
- Do not introduce paid services, billing activation, or hidden usage costs without explicit approval.
- Use least-privilege GitHub permissions and the existing CI workflow where possible.
- Do not merge, deploy, publish a release, send messages, or perform other irreversible external actions without explicit permission.
- Ask before security-sensitive changes or actions with external side effects.
- Do not claim a test, deployment, upload, or verification succeeded without observing its result.

## 7. Explicit exclusions

- Do not begin Stage 2 Task 2.4 (measured silence candidates with human review) unless the user separately authorises it.
- Do not implement video-editor features as part of this configuration work.
- Do not change the renderer architecture, Cloudflare Worker deployment, database migrations, or application behavior for workflow documentation.
- Do not modify `main`, use the Sparkle Clean repository, or move the project.
- Do not add an unusable agent framework or imply that Actions provides AI agents.

## 8. Acceptance criteria

- Persistent repository instructions and focused workflow/review documents exist on `video-editor-lab`.
- Instructions accurately describe available tools and the lack of an independent-agent runtime.
- Repository, branch, budget, security, and approval constraints are explicit.
- Existing application features and CI configuration remain unchanged.
- Stage 2 Task 2.4 remains unstarted.
- Every created document is read back from GitHub and the final changed-file list is checked.
