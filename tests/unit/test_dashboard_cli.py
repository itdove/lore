from __future__ import annotations

from unittest import mock

import pytest

from lore.cli import main


class TestDashboardSubcommand:
    def test_dashboard_help(self, capsys):
        try:
            main(["dashboard", "--help"])
        except SystemExit:
            pass
        captured = capsys.readouterr()
        assert "--port PORT" in captured.out

    def test_dashboard_args_parsed(self):
        with mock.patch("lore.dashboard.launch") as mock_launch:
            try:
                main(["dashboard", "--port", "9999", "--host", "0.0.0.0"])
            except SystemExit:
                pass

            assert mock_launch.called
            mock_launch.assert_called_once_with(host="0.0.0.0", port=9999)

    def test_dashboard_missing_nicegui(self):
        with mock.patch(
            "lore.dashboard.launch",
            side_effect=ImportError("No module named 'nicegui'"),
        ):
            with pytest.raises(ImportError, match="nicegui"):
                main(["dashboard"])

    def test_dashboard_in_handlers(self):
        import lore.cli as cli_mod

        assert hasattr(cli_mod, "_cmd_dashboard")
