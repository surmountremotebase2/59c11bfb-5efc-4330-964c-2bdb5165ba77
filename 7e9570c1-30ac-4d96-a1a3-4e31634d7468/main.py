from surmount.base_class import Strategy, TargetAllocation
from statistics import stdev
from surmount.technical_indicators import SMA


class TradingStrategy(Strategy):

    # ============================================================
    # CONFIGURATION (edit these to change behavior)
    # ============================================================

    # Pair assets (relative-value signal)
    PAIR_ASSET_1 = "GOOG"
    PAIR_ASSET_2 = "AAPL"

    # Market/beta assets
    BASE_ASSET = "SPY"
    LEVERAGED_ASSET = "TQQQ"

    # 1) SMA periods
    SMA_FAST_PERIOD = 20
    SMA_SLOW_PERIOD = 32

    # Ratio threshold
    RATIO_STD_DIVISOR = 1.2

    # NEW: rolling lookback for ratio mean/stdev (initial value = 250, configurable)
    RATIO_LOOKBACK_DAYS = 250

    # 2) Initial default asset weights
    DEFAULT_WEIGHTS = {
        "PAIR1": 0.0,
        "PAIR2": 0.0,
        "BASE": 0.8,
        "LEVER": 0.2,
    }

    # 3) Rotation weights
    ROTATE_TO_PAIR2_WEIGHTS = {
        "PAIR1": 0.0,
        "PAIR2": 0.85,
        "BASE": 0.10,
        "LEVER": 0.05,
    }

    ROTATE_TO_PAIR1_WEIGHTS = {
        "PAIR1": 0.85,
        "PAIR2": 0.0,
        "BASE": 0.10,
        "LEVER": 0.05,
    }

    # 4) Market overlay weights
    OVERLAY_LEVEL1_FAST_VS_SLOW = 0.99
    OVERLAY_LEVEL2_FAST_VS_SLOW = 0.98

    OVERLAY_LEVEL1_WEIGHTS = {
        "BASE": 0.3,
        "LEVER": 0.1,
        "PAIR_SCALE": 1 / 3,
    }

    OVERLAY_LEVEL2_WEIGHTS = {
        "BASE": 0.2,
        "LEVER": 0.3,
    }

    # ============================================================
    # Surmount required properties
    # ============================================================

    @property
    def assets(self):
        return [
            self.PAIR_ASSET_1,
            self.PAIR_ASSET_2,
            self.BASE_ASSET,
            self.LEVERAGED_ASSET,
        ]

    @property
    def interval(self):
        return "1day"

    # ============================================================
    # Helpers
    # ============================================================

    def _materialize_weights(self, template: dict) -> dict:
        return {
            self.PAIR_ASSET_1: float(template.get("PAIR1", 0.0)),
            self.PAIR_ASSET_2: float(template.get("PAIR2", 0.0)),
            self.BASE_ASSET: float(template.get("BASE", 0.0)),
            self.LEVERAGED_ASSET: float(template.get("LEVER", 0.0)),
        }

    def _ratio_series(self, ohlcv_slice: list) -> list:
        """
        Build GOOG/AAPL (PAIR1/PAIR2) close-price ratio series over the provided slice.
        Assumes each element has both tickers present.
        """
        return [
            day[self.PAIR_ASSET_1]["close"] / day[self.PAIR_ASSET_2]["close"]
            for day in ohlcv_slice
        ]

    # ============================================================
    # Strategy logic
    # ============================================================

    def run(self, data):
        ohlcv = data["ohlcv"]

        # Need enough data for ratio window AND SMA windows
        min_needed = max(4, self.RATIO_LOOKBACK_DAYS, self.SMA_SLOW_PERIOD)
        if len(ohlcv) < min_needed:
            return TargetAllocation({})

        # -------------------------
        # Rolling ratio statistics
        # -------------------------
        lookback = min(self.RATIO_LOOKBACK_DAYS, len(ohlcv))
        window = ohlcv[-lookback:]  # last N days
        ratio = self._ratio_series(window)

        # If stdev can't be computed (e.g., len==1), avoid trading
        if len(ratio) < 2:
            return TargetAllocation({})

        mean_ratio = sum(ratio) / len(ratio)
        dev_ratio = stdev(ratio)

        upper_band = mean_ratio + dev_ratio / self.RATIO_STD_DIVISOR
        lower_band = mean_ratio - dev_ratio / self.RATIO_STD_DIVISOR

        # Default allocation
        weights = self._materialize_weights(self.DEFAULT_WEIGHTS)

        # Rotation logic based on rolling bands
        if ratio[-1] > upper_band:
            weights = self._materialize_weights(self.ROTATE_TO_PAIR2_WEIGHTS)
        elif ratio[-1] < lower_band:
            weights = self._materialize_weights(self.ROTATE_TO_PAIR1_WEIGHTS)

        # -------------------------
        # Market overlay (SMA-based)
        # -------------------------
        ma_fast_series = SMA(self.BASE_ASSET, ohlcv, self.SMA_FAST_PERIOD)
        ma_slow_series = SMA(self.BASE_ASSET, ohlcv, self.SMA_SLOW_PERIOD)

        if not ma_fast_series or not ma_slow_series:
            return TargetAllocation({})

        ma_fast = ma_fast_series[-1]
        ma_slow = ma_slow_series[-1]

        if ma_fast < self.OVERLAY_LEVEL1_FAST_VS_SLOW * ma_slow:
            pair_scale = float(self.OVERLAY_LEVEL1_WEIGHTS.get("PAIR_SCALE", 1.0))
            weights[self.PAIR_ASSET_1] *= pair_scale
            weights[self.PAIR_ASSET_2] *= pair_scale

            weights[self.BASE_ASSET] = float(self.OVERLAY_LEVEL1_WEIGHTS["BASE"])
            weights[self.LEVERAGED_ASSET] = float(self.OVERLAY_LEVEL1_WEIGHTS["LEVER"])

            if ma_fast < self.OVERLAY_LEVEL2_FAST_VS_SLOW * ma_slow:
                weights[self.BASE_ASSET] = float(self.OVERLAY_LEVEL2_WEIGHTS["BASE"])
                weights[self.LEVERAGED_ASSET] = float(self.OVERLAY_LEVEL2_WEIGHTS["LEVER"])

        return TargetAllocation(weights)