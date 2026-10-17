"""Unit tests for src/f1_predictions/utils/chart_exporter.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from f1_predictions.utils.chart_exporter import (
    chart_to_base64,
    export_position_chart_png,
)


class TestChartToBase64:
    """Tests for chart_to_base64."""

    def test_encodes_file_contents_to_base64(self, tmp_path: Path) -> None:
        file_path = tmp_path / "test.png"
        file_path.write_bytes(b"dummy image data")

        encoded = chart_to_base64(file_path)
        assert isinstance(encoded, str)
        assert len(encoded) > 0


class TestExportPositionChartPng:
    """Tests for export_position_chart_png."""

    def test_missing_columns_raises_value_error(self, tmp_path: Path) -> None:
        df = pd.DataFrame({"Driver": ["VER"], "LapNumber": [1]})
        with pytest.raises(ValueError, match="missing required columns"):
            export_position_chart_png(df, tmp_path / "chart.png")

    @patch("plotly.graph_objects.Figure.write_image")
    def test_renders_and_exports_chart(
        self, mock_write_image: MagicMock, tmp_path: Path
    ) -> None:
        df = pd.DataFrame(
            {
                "Driver": ["VER", "VER", "HAM", "HAM"],
                "LapNumber": [1, 2, 1, 2],
                "Predicted_Position": [1, 1, 2, 2],
            }
        )
        out_file = tmp_path / "out" / "chart.png"
        result = export_position_chart_png(df, out_file, gp_name="Monaco GP")

        assert result == out_file
        assert mock_write_image.called
