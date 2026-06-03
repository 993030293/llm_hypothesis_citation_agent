# Unicode Rerun Note

The first full generalization audit completed 14 of 15 cases. The only failed case was
`neuroscience_deeplabcut`, caused by a Windows console encoding failure while printing a
PDF title containing a Unicode ligature character.

Fix applied:

- `agent/workflow.py` now configures stdout/stderr as UTF-8 at startup.
- `scripts/generalization_audit.py` now runs child Python processes with
  `PYTHONIOENCODING=utf-8:replace` and decodes captured output as UTF-8.
- `tests/test_generalization_audit.py` includes a subprocess Unicode-output regression test.

Post-fix rerun:

- Audit directory: `outputs/generalization_audits/20260601_015740`
- Submission copy: `submission/generalization_audit/reruns/neuroscience_deeplabcut_after_unicode_fix`
- Result: workflow success, artifact_complete=True, Green=3, Yellow=1, Red=2
- Failure report: no failures recorded.

This preserves the original failure evidence while showing that the boundary was identified,
fixed, tested, and rerun successfully.
