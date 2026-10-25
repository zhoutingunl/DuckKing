# Repository instructions

- Use feature branches and pull requests for every change after the empty `v0` baseline. Never push application changes directly to main or move v0.
- Keep commits truthful: no fabricated contributors, authors, tests, cloud sessions, physics results, or backdated history.
- Preserve an obvious distinction between original animation preview, official robotd/MuJoCo connection, and live Linx cloud voice.
- Do not silently fall back from a failed real backend to preview, or label local scripted behavior as a cloud response.
- Keep credentials and device identities out of tracked files and API responses/logs.
- Add meaningful tests for motion cancellation, bounded actions, protocol framing, and failure handling. Run relevant checks before merging.
- Document architecture, setup, current limitations, and third-party sources. Keep docs synchronized with actual tested behavior.
