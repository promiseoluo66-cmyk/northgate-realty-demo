# Specialist Review Checklist

Use these perspectives after implementation and before reporting completion. They are structured review responsibilities performed by the same ChatGPT session. They are not separate AI agents or independent workers.

For every finding, record: **severity**, **affected path**, **evidence**, **required correction**, and **verification result**.

## 1. Lead architect review

- Does the change follow the approved design and existing project architecture?
- Does it reuse existing components and interfaces instead of duplicating functionality?
- Are boundaries between application, Studio, Worker, storage, and CI preserved?
- Is the change limited to the approved scope?
- Are future dependencies and compatibility assumptions explicit?

## 2. Research and documentation review

- Were current external APIs and platform behaviors checked with Context7 when needed?
- Are official or authoritative sources preferred?
- Are version assumptions and limitations accurate?
- Are claims supported by observed repository state or cited documentation?
- Is any uncertain behavior clearly labelled rather than guessed?

## 3. Implementation review

- Does each changed file have one clear responsibility?
- Are names, interfaces, data formats, and error behavior consistent with neighboring code?
- Is existing functionality preserved?
- Is the change minimal, readable, and maintainable?
- Are unrelated refactors and dependencies avoided?

## 4. Debugging and failure review

- Are failure paths and invalid inputs considered?
- Are errors surfaced clearly without hiding the underlying cause?
- Are partial operations, retries, and cleanup safe where relevant?
- Was the root cause addressed rather than only the visible symptom?
- Are known limitations and unresolved failures reported?

## 5. Testing and verification review

- Were tests written before implementation for code behavior changes?
- Was the expected failing result observed before the implementation?
- Were focused tests and the appropriate broader suite run?
- Were outputs actually inspected?
- Are CI results tied to the correct repository, branch, commit, and run?
- Are historical results clearly distinguished from fresh verification?
- If CI was not run, is that stated plainly?

## 6. Security and cost review

- Are secrets, tokens, personal data, and credentials excluded from code and logs?
- Are permissions least-privilege?
- Are external network calls, file access, and user-controlled inputs handled safely?
- Does the change introduce a paid service, billing requirement, quota risk, or hidden usage?
- Are destructive actions, deployments, releases, and external communications gated by explicit approval?
- Does the work remain within the $0 current budget?

## 7. Final QA review

- Is the diff limited to the approved files and task?
- Are project instructions, plans, links, and references consistent?
- Are regressions or duplicate implementations introduced?
- Are all acceptance criteria met with evidence?
- Is all work confined to `promiseoluo66-cmyk/northgate-realty-demo` on `video-editor-lab`, with `main` untouched?
- Is Stage 2 Task 2.4 (measured silence candidates with human review) still unstarted, and is all other explicitly excluded work untouched?
- Does the final report list exact files, commit, checks, limitations, and blockers?

## Finding severity

- **Critical:** security exposure, data loss, destructive behavior, or a severe project-breaking defect. Stop and correct before completion.
- **Important:** material functional regression, incorrect behavior, or a significant acceptance-criteria failure. Correct before completion.
- **Minor:** non-blocking polish, clarity, or maintainability improvement. Record and defer unless the user approves additional scope.

## Review outcome

Record one of:

- **PASS:** no Critical or Important findings; acceptance criteria are supported by evidence.
- **PASS WITH DEFERRED MINORS:** no Critical or Important findings; Minor findings are listed for the user.
- **BLOCKED:** one or more Critical or Important findings remain, or required evidence/permissions are unavailable.

Do not describe a self-review as an independent review. State that the same ChatGPT session performed the specialist perspectives.
