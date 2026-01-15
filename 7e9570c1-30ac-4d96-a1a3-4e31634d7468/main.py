from surmount.base_class import Strategy, TargetAllocation
from statistics import stdev
from surmount.technical_indicators import SMA


class TradingStrategy(Strategy):

    # =========================
    # CONFIGURATION
    # =========================
    PAIR_ASSET_1 = "GOOG"
    PAIR_ASSET_2 = "AAPL"

    BASE_ASSET = "SPY"
    LEVERAGED_ASSET = "TQQQ"

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

    def run(self, data):

        ohlcv = data["ohlcv"]

        if len(ohlcv) < 4:
            return TargetAllocation({})

        # =========================
        # BUILD PRICE RATIO SERIES
        # =========================
        ratio = [
            ohlcv[i][self.PAIR_ASSET_1]["close"] /
            ohlcv[i][self.PAIR_ASSET_2]["close"]
            for i in range(len(ohlcv))
        ]

        mean_ratio = sum(ratio) / len(ratio)
        dev_ratio = stdev(ratio)

        # =========================
        # DEFAULT ALLOCATION
        # =========================
        weights = {
            self.PAIR_ASSET_1: 0.0,
            self.PAIR_ASSET_2: 0.0,
            self.BASE_ASSET: 0.8,
            self.LEVERAGED_ASSET: 0.2,
        }

        # =========================
        # RELATIVE-VALUE SIGNAL
        # =========================
        upper_band = mean_ratio + dev_ratio / 1.2
        lower_band = mean_ratio - dev_ratio / 1.2

        if ratio[-1] > upper_band:
            # Asset 1 expensive → rotate into Asset 2
            weights[self.PAIR_ASSET_2] = 0.85
            weights[self.BASE_ASSET] = 0.10
            weights[self.LEVERAGED_ASSET] = 0.05

        elif ratio[-1] < lower_band:
            # Asset 1 cheap → rotate into Asset 1
            weights[self.PAIR_ASSET_1] = 0.85
            weights[self.BASE_ASSET] = 0.10
            weights[self.LEVERAGED_ASSET] = 0.05

        # =========================
        # TREND FILTER (SPY)
        # =========================
        ma20 = SMA(self.BASE_ASSET, ohlcv, 20)
        ma32 = SMA(self.BASE_ASSET, ohlcv, 32)

        if not ma20 or not ma32:
            return TargetAllocation({})

        ma20 = ma20[-1]
        ma32 = ma32[-1]

        if ma20 < 0.99 * ma32:
            weights[self.PAIR_ASSET_1] /= 3
            weights[self.PAIR_ASSET_2] /= 3
            weights[self.BASE_ASSET] = 0.3
            weights[self.LEVERAGED_ASSET] = 0.1

            if ma20 < 0.98 * ma32:
                weights[self.BASE_ASSET] = 0.2
                weights[self.LEVERAGED_ASSET] = 0.3

        return TargetAllocation(weights)