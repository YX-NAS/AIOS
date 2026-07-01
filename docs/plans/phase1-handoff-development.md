# Phase 1 Handoff Development Plan

## Objective

Deliver the first executable version of the semi-automatic workflow.

The concrete completion condition is:

- one task can be split, routed, packed, handed off to a human-switched model session, completed, and written back into AIOS;
- the workflow is available from CLI and Web UI;
- automated tests cover the new handoff path.

## Scope

- Add a task handoff artifact under `.aios/handoffs/`.
- Add a CLI entrypoint to generate one handoff file.
- Add a Web API entrypoint to generate one handoff file.
- Add a Web UI action to generate and copy the handoff content.
- Update documentation for the semi-automatic flow.

## Non-goals

- No automatic `ccswitch` control.
- No automatic Codex or Claude Code execution.
- No automatic Git commit or merge flow.
- No multi-task scheduler in this phase.

## Design

The new handoff layer sits on top of existing task, route, and pack modules.

Flow:

1. Read task data from `tasks.json`.
2. Resolve recommended model from router.
3. Reuse or rebuild the Context Pack.
4. Generate a handoff markdown file with:
   - task metadata
   - execution model
   - fallback model
   - manual execution steps
   - acceptance criteria
   - routing reason
   - embedded Context Pack
5. Expose the handoff through CLI and Web UI.

## Review conclusion

This is the smallest correct step.

- It avoids coupling AIOS to unstable model-switch automation.
- It reduces repeated manual work immediately.
- It preserves the current file-based architecture.
- It leaves a clean adapter point for future scheduler work.

## Test plan

Automated tests:

1. CLI init test:
   - verify `.aios/handoffs/` exists after initialization.
2. CLI handoff test:
   - create task
   - generate handoff
   - verify handoff file exists
   - verify file contains task metadata and Context Pack section
3. Web API handoff test:
   - call `/api/handoff`
   - verify response contains handoff path and content
   - verify content includes manual execution steps

Manual acceptance:

1. Start Web UI on a test project.
2. Initialize and scan project.
3. Split a goal into tasks.
4. Select one task and click the handoff button.
5. Confirm clipboard content includes model, steps, and Context Pack.
6. Complete the task and verify `.aios/changelog.md` and `.aios/memory.md` are updated.

## Acceptance criteria

- `aios handoff TASK-ID` succeeds.
- Web UI can generate and copy a handoff for the selected task.
- Existing `pack` and `complete` flows still work.
- `python -m pytest` passes.
