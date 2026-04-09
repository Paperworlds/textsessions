# Report: 008 — TUI error handling: toast notifications for failed actions
Date: 2026-04-08T00:00:00Z
Status: DONE

## Changes
- a827f26 Add toast notifications for TUI action errors and successes (textsessions)

## Test results
- textsessions: 86 tests passed

## Notes for next prompt
- `app.notify()` severity accepts "information", "warning", "error"
- Success toasts use `severity="information"` (brief 1-2 word messages)
- Error toasts include the exception string for debuggability
- `action_resume_session` captures returncode outside `with self.suspend()` block — the notify call must happen after re-entering Textual context, which is already the case since `with self.suspend()` exits before the notify
