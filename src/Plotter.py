import functools
import sys
from pathlib import Path
from typing import Literal, Optional

import matplotlib.pyplot as plt
import mplfinance as mpf

from loaders.AbstractLoader import AbstractLoader


class Plotter:
    idx = 0
    idx_str = ""
    default_backend = plt.get_backend()

    def __init__(
        self,
        data,
        loader: AbstractLoader,
        save_folder: Optional[Path] = None,
        mode: Literal["default", "expand"] = "default",
    ):
        self.save_folder = save_folder
        self.mode = mode
        self.loader = loader
        self.timeframe = loader.tf

        self.plot_args = {
            "type": "candle",
            "style": "tradingview",
            "scale_padding": {
                "left": 0.05,
                "right": 0.6,
                "top": 0.35,
                "bottom": 0.7,
            },
            "alines": {"linewidths": 0.8, "alpha": 0.7},
        }

        if save_folder:
            # Save images with non interactive backend and
            # switch off interactive mode
            self.data = None

            # Switch to a Non GUI backend to work with threads
            plt.switch_backend("AGG")
            plt.ioff()
        else:
            plt.ion()
            plt.switch_backend(self.default_backend)
            self.data = list(data.values()) if isinstance(data, dict) else data
            self.len = len(data) - 1

            self.plot_args.update(dict(figscale=1, returnfig=True))

            print("\nChart Controls\n\tq: quit\n\tn: Next\n\tp: Previous")

    def save(self, dct):

        assert isinstance(self.save_folder, Path)

        sym = dct["sym"].upper()
        pattern = dct["pattern"]
        lines = dct["lines"]

        df = self.loader.get(sym)

        if df is None:
            raise ValueError(f"Unable to load data for {sym}")

        if pattern in ("Symmetric", "Ascending", "Descending"):
            colors = "midnightblue"
        else:
            colors = ("green",) + ("midnightblue",) * (len(lines) - 1)

        save_path = self.save_folder / f"{sym}_{pattern}_{self.timeframe}.png"

        self.plot_args.update(
            dict(
                title=f"{sym} - {pattern} - {self.timeframe.capitalize()}",
                figscale=1.2,
                savefig=dict(
                    fname=save_path,
                    dpi=100,
                ),
            )
        )

        self.plot_args["scale_padding"]["right"] = 0.8

        self.plot_args["alines"].update({"alines": lines, "colors": colors})

        mpf.plot(df, **self.plot_args)

    def plot(self, idx=None):
        if self.data is None:
            raise TypeError("Missing dict data")

        if idx:
            self.idx = idx

        stmt = f"{self.idx} of {self.len}"
        print(stmt, flush=True, end="\r" * len(stmt))

        dct = self.data[self.idx]
        sym = dct["sym"].upper()
        pattern = dct["pattern"]

        df = self.loader.get(sym)

        if df is None:
            raise ValueError(f"Unable to load data for {sym}")

        if self.mode == "expand":
            start = df.index.get_loc(dct["start"])
            end = df.index.get_loc(dct["end"])

            if isinstance(start, slice):
                start = start.start

            if isinstance(end, slice):
                end = end.start

            assert isinstance(start, int)
            assert isinstance(end, int)

            start = max(start - 120, 0)
            end = min(end + 120, len(df))

            df = df.iloc[start:end]

        if pattern in ("Symmetric", "Ascending", "Descending"):
            lines = dct["extra_lines"]
            colors = "midnightblue"
        else:
            lines = list(dct.get("extra_lines", [])) + list(dct["lines"])
            colors = ("green",) + ("midnightblue",) * (len(lines) - 1)

        self.plot_args["title"] = (
            f"{sym} - {pattern} - {self.timeframe.capitalize()}"
        )

        self.plot_args["alines"].update({"alines": lines, "colors": colors})

        self.fig, axs = mpf.plot(df, **self.plot_args)

        self.main_ax = axs[0]

        axs[0].set_title(
            stmt, loc="left", color="black", fontdict={"fontweight": "bold"}
        )

        self._annotate_fn = functools.partial(
            axs[0].annotate,
            textcoords="offset points",
            horizontalalignment="center",
            fontweight="bold",
            color="midnightblue",
        )

        if pattern in ("UPTL", "DNTL"):
            line_data = dct["touch_points"]
        else:
            line_data = dct["lines"]

        self._annotations(df, line_data, dct.get("y_close", None))

        self.fig.canvas.mpl_connect("key_press_event", self._on_key_press)

        window_manager = plt.get_current_fig_manager()

        if window_manager:
            if "win" in sys.platform:
                try:
                    # Only works with tkAgg backend
                    window_manager.window.state("zoomed")
                except AttributeError:
                    window_manager.full_screen_toggle()
            else:
                window_manager.full_screen_toggle()

        mpf.show(block=True)

    def _annotations(self, df, lines, last_close=None):
        annotate_txt = "ABCDEFGHIJKLM"

        last_idx = df.index[-1]
        last_pos = df.index.get_loc(last_idx)

        if not last_close:
            last_close = df.at[last_idx, "Close"]

        # Annotate the close price
        self._annotate_fn(
            annotate_txt[len(lines)],
            xy=(last_pos, last_close),
            xytext=(10, -10),
        )

        for i, line in enumerate(lines):

            x, y = line[0] if isinstance(line[0], (list, tuple)) else line

            loc = 5 if y == df.at[x, "High"] else -10

            self._annotate_fn(
                text=annotate_txt[i],
                xy=(df.index.get_loc(x), y),
                xytext=(0, loc),
            )

    def _on_key_press(self, event):
        key = event.key

        if key.isdigit():
            self.idx_str += key

            return self._alert(f"{self.idx_str}j")

        if key not in ("n", "p", "j", "escape"):
            return

        if key == "escape":
            self.idx_str = ""

            return self._alert()

        if key == "j":
            if self.idx_str == "":
                return

            idx = int(self.idx_str)

            if idx > self.len:
                self.idx_str = ""
                return self._alert()

            self.idx = idx

        if key == "n":
            if self.idx >= self.len:
                return self._alert("At Last Chart")

            self.idx += 1

        if key == "p":
            if self.idx == 0:
                return self._alert("At First Chart")

            self.idx -= 1

        self.idx_str = ""
        plt.close("all")
        self.plot()

    def _alert(self, string=""):
        return self.main_ax.set_title(
            string,
            loc="right",
            color="crimson",
            fontdict={"fontweight": "bold"},
        )
