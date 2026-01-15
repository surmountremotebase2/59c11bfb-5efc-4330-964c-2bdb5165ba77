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

    # 1) SMA periods (keep initial values the same)
    SMA_FAST_PERIOD = 20
    SMA_SLOW_PERIOD = 32

    # Ratio threshold (keep same behavior: dev / 1.2)
    RATIO_STD_DIVISOR = 1.2

    # 2) Initial default asset weights (keep initial values the same)
    DEFAULT_WEIGHTS = {
        "PAIR1": 0.0,
        "PAIR2": 0.0,
        "BASE": 0.8,
        "LEVER": 0.2,
    }

    # 3) Rotation weights (keep initial values the same)
    # When PAIR_ASSET_1 is "expensive" vs PAIR_ASSET_2 -> rotate into PAIR_ASSET_2
    ROTATE_TO_PAIR2_WEIGHTS = {
        "PAIR1": 0.0,
        "PAIR2": 0.85,
        "BASE": 0.10,
        "LEVER": 0.05,
    }

    # When PAIR_ASSET_1 is "cheap" vs PAIR_ASSET_2 -> rotate into PAIR_ASSET_1
    ROTATE_TO_PAIR1_WEIGHTS = {
        "PAIR1": 0.85,
        "PAIR2": 0.0,
        "BASE": 0.10,
        "LEVER": 0.05,
    }

    # 4) Market overlay weights (keep initial values the same)
    # Overlay trigger thresholds (keep initial values the same)
    OVERLAY_LEVEL1_FAST_VS_SLOW = 0.99  # ma_fast < 0.99 * ma_slow
    OVERLAY_LEVEL2_FAST_VS_SLOW = 0.98  # ma_fast < 0.98 * ma_slow

    # Level 1 overlay: reduce pair exposure to 1/3, set BASE/LEVER
    OVERLAY_LEVEL1_WEIGHTS = {
        "BASE": 0.3,
        "LEVER": 0.1,
        "PAIR_SCALE": 1 / 3,   # scale applied to current PAIR1/PAIR2 weights
    }

    # Level 2 overlay (nested inside level 1): override BASE/LEVER only
    OVERLAY_LEVEL2_WEIGHTS = {
        "BASE": 0.2,
        "LEVER": 0.3,
        # PAIR_SCALE remains whatever Level 1 applied (same as original logic)
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
        """
        Convert a template with keys {PAIR1, PAIR2, BASE, LEVER} into a ticker-weight dict.
        """
        return {
            self.PAIR_ASSET_1: float(template.get("PAIR1", 0.0)),
            self.PAIR_ASSET_2: float(template.get("PAIR2", 0.0)),
            self.BASE_ASSET: float(template.get("BASE", 0.0)),
            self.LEVERAGED_ASSET: float(template.get("LEVER", 0.0)),
        }

    # ============================================================
    # Strategy logic
    # ============================================================

    def run(self, data):
        ohlcv = data["ohlcv"]

        # Minimal data gate (kept same)
        if len(ohlcv) < 4:
            return TargetAllocation({})

        # Build ratio series across all available history (kept same)
        ratio = [
            ohlcv[i][self.PAIR_ASSET_1]["close"] / ohlcv[i][self.PAIR_ASSET_2]["close"]
            for i in range(len(ohlcv))
        ]

        mean_ratio = sum(ratio) / len(ratio)
        dev_ratio = stdev(ratio)

        upper_band = mean_ratio + dev_ratio / self.RATIO_STD_DIVISOR
        lower_band = mean_ratio - dev_ratio / self.RATIO_STD_DIVISOR

        # Start from default weights (kept same)
        weights = self._materialize_weights(self.DEFAULT_WEIGHTS)

        # Rotation logic (kept same, but parameterized)
        if ratio[-1] > upper_band:
            weights = self._materialize_weights(self.ROTATE_TO_PAIR2_WEIGHTS)
        elif ratio[-1] < lower_band:
            weights = self._materialize_weights(self.ROTATE_TO_PAIR1_WEIGHTS)

        # Market overlay (SMA-based) (kept same, but parameterized)
        ma_fast_series = SMA(self.BASE_ASSET, ohlcv, self.SMA_FAST_PERIOD)
        ma_slow_series = SMA(self.BASE_ASSET, ohlcv, self.SMA_SLOW_PERIOD)

        if not ma_fast_series or not ma_slow_series:
            return TargetAllocation({})

        ma_fast = ma_fast_series[-1]
        ma_slow = ma_slow_series[-1]

        if ma_fast < self.OVERLAY_LEVEL1_FAST_VS_SLOW * ma_slow:
            # Scale pair weights
            pair_scale = float(self.OVERLAY_LEVEL1_WEIGHTS.get("PAIR_SCALE", 1.0))
            weights[self.PAIR_ASSET_1] *= pair_scale
            weights[self.PAIR_ASSET_2] *= pair_scale

            # Set BASE / LEVER per overlay level 1
            weights[self.BASE_ASSET] = float(self.OVERLAY_LEVEL1_WEIGHTS["BASE"])
            weights[self.LEVERAGED_ASSET] = float(self.OVERLAY_LEVEL1_WEIGHTS["LEVER"])

            # If deeper downtrend, override BASE/LEVER (kept same)
            if ma_fast < self.OVERLAY_LEVEL2_FAST_VS_SLOW * ma_slow:
                weights[self.BASE_ASSET] = float(self.OVERLAY_LEVEL2_WEIGHTS["BASE"])
                weights[self.LEVERAGED_ASSET] = float(self.OVERLAY_LEVEL2_WEIGHTS["LEVER"])

        return TargetAllocation(weights)