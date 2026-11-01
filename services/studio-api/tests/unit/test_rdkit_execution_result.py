"""An exit code or JSON document cannot override execution failure flags."""

from __future__ import annotations

import pytest
from workers.common.executor import ExecResult, IsolationProfile

from engine_adapter_rdkit import EngineError, RDKitAdapter


@pytest.mark.parametrize(
    "cancelled,timed_out,exit_code,stdout,code",
    [
        (True, False, 0, '{"ok": true}', "CANCELLED"),
        (False, True, 0, '{"ok": true}', "TIMED_OUT"),
        (False, False, 1, '{"ok": true}', "INTERNAL"),
        (False, False, 0, "not JSON", "INTERNAL"),
    ],
)
def test_failure_flags_win_over_stdout(cancelled, timed_out, exit_code, stdout, code):
    class Backend:
        profile = IsolationProfile("test", {"network_denied": False})

        def run(self, *args, **kwargs):
            return ExecResult(
                exit_code=exit_code,
                timed_out=timed_out,
                cancelled=cancelled,
                wall_seconds=0.1,
                stdout=stdout,
                stderr="private worker diagnostics",
                truncated=False,
                profile=self.profile,
            )

    result = RDKitAdapter(backend=Backend()).describe(smiles="CCO")
    assert isinstance(result, EngineError)
    assert result.code == code
    assert result.execution["profile"] == "test"
    assert result.execution["enforced"]["network_denied"] is False
    assert "private worker diagnostics" not in result.message
    assert not hasattr(result, "descriptors")
