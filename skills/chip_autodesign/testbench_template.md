# Testbench Template

Every generated testbench should:

- Be self-checking and print `ALL TESTS PASSED` only when all checks pass.
- Emit a VCD waveform under `wave/`.
- Include reset, nominal behavior, boundary behavior, and at least one signed or
  protocol edge case where relevant.
- Fail with `$fatal(1)` and a useful message on mismatches.
- Keep reference calculations local and deterministic.
