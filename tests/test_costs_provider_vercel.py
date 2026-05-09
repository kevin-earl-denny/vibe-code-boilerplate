"""Tests for Vercel cost provider."""

from unittest.mock import MagicMock, patch

from lib.vibe.costs.providers.vercel import VercelCostProvider


class TestVercelCostProvider:
    def test_name(self):
        p = VercelCostProvider()
        assert p.name == "vercel"
        assert p.display_name == "Vercel"

    def test_env_vars(self):
        assert VercelCostProvider().get_env_vars() == ["VERCEL_TOKEN"]

    def test_check_credentials_no_token(self):
        with patch.dict("os.environ", {}, clear=True):
            p = VercelCostProvider()
            assert p.check_credentials() is False

    @patch("lib.vibe.costs.providers.vercel.requests.get")
    def test_check_credentials_valid(self, mock_get):
        mock_get.return_value = MagicMock(status_code=200)
        with patch.dict("os.environ", {"VERCEL_TOKEN": "test_token"}):
            p = VercelCostProvider()
            assert p.check_credentials() is True

    @patch("lib.vibe.costs.providers.vercel.requests.get")
    def test_check_credentials_invalid(self, mock_get):
        mock_get.return_value = MagicMock(status_code=401)
        with patch.dict("os.environ", {"VERCEL_TOKEN": "bad_token"}):
            p = VercelCostProvider()
            assert p.check_credentials() is False

    @patch("lib.vibe.costs.providers.vercel.requests.get")
    def test_get_current_costs(self, mock_get):
        jsonl_body = (
            '{"BilledCost": 5.00, "ServiceName": "Bandwidth", "ConsumedQuantity": 100, "PricingUnit": "GB"}\n'
            '{"BilledCost": 3.47, "ServiceName": "Serverless Functions", "ConsumedQuantity": 50000, "PricingUnit": "invocations"}\n'
        )
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = jsonl_body
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict("os.environ", {"VERCEL_TOKEN": "test_token"}):
            p = VercelCostProvider(config={"plan_cost": 20.0})
            report = p.get_current_costs("2026-02")

        assert report.provider == "Vercel"
        assert report.total == 8.47
        assert report.plan_cost == 20.0
        assert report.overage == 0  # Under plan cost
        assert len(report.line_items) == 2
        assert report.line_items[0].name == "Bandwidth"

    @patch("lib.vibe.costs.providers.vercel.requests.get")
    def test_get_current_costs_with_overage(self, mock_get):
        jsonl_body = '{"BilledCost": 25.00, "ServiceName": "Bandwidth", "ConsumedQuantity": 500, "PricingUnit": "GB"}\n'
        mock_resp = MagicMock()
        mock_resp.text = jsonl_body
        mock_resp.raise_for_status = MagicMock()
        mock_get.return_value = mock_resp

        with patch.dict("os.environ", {"VERCEL_TOKEN": "test_token"}):
            p = VercelCostProvider(config={"plan_cost": 20.0})
            report = p.get_current_costs("2026-02")

        assert report.total == 25.0
        assert report.overage == 5.0

    @patch("lib.vibe.costs.providers.vercel.requests.get")
    def test_get_current_costs_api_error(self, mock_get):
        import requests

        mock_get.side_effect = requests.RequestException("Network error")

        with patch.dict("os.environ", {"VERCEL_TOKEN": "test_token"}):
            p = VercelCostProvider()
            report = p.get_current_costs("2026-02")

        assert report.total == 0.0
        assert report.is_estimated is True

    def test_month_range(self):
        start, end = VercelCostProvider._month_range("2026-02")
        assert start == "2026-02-01T00:00:00Z"
        assert end == "2026-03-01T00:00:00Z"

    def test_month_range_december(self):
        start, end = VercelCostProvider._month_range("2026-12")
        assert start == "2026-12-01T00:00:00Z"
        assert end == "2027-01-01T00:00:00Z"

    def test_parse_empty_body(self):
        with patch.dict("os.environ", {"VERCEL_TOKEN": "test"}):
            p = VercelCostProvider()
            report = p._parse_charges("", "2026-02")
        assert report.total == 0.0
        assert report.line_items == []
