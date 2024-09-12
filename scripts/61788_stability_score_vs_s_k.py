# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import functions
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

output_folder = "/home/nick/Pictures/plots/61788_stability_score"
functions.makedir(output_folder)
# %% stability score plots for different k and s
s_vals = [0.2, 1.4]
k_vals = [0.2, 0.6, 1.5, 2.5]

plt.figure()
x = np.linspace(0, 1, 1000)

for s in s_vals:
    for k in k_vals:
        ss = [functions.map_between_zero_and_one(x_val, s=s, k=k) for x_val in x]

        plt.plot(x, ss, lw=3, label=f"k={k}, s={s}")
        plt.xlabel("Normalized 12-month rolling standard dev. [kr]")
        plt.ylabel("Stability-score [0-1]")
        plt.title("Stability score vs. std")
plt.legend(loc=4)
plt.savefig(output_folder + "/stability_score")
