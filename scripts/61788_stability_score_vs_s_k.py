# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os

import functions
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()


output_folder = os.environ["HOME"] + "/Pictures/plots/61788_stability_score"
functions.makedir(output_folder)

# %% stability score plots for different k and s
s_vals = [0.2, 0.4, 0.6]
k_vals = [0.6, 1.5, 2.5]

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


# %% Plot some standard deviations
cprs = [
    279,  # stable
    648,  # stable
    24,  # acceptable outliers
    195,  # acceptable outliers
    13,  # unstable
    241,  # unstable
]

df_a, df_b = functions.load_data()

for cpr in cprs:
    plt.figure(figsize=(16, 6))
    functions.plot_income(cpr, df_a, df_b)

    std_norm = df_a.loc[cpr, :].std() / df_a.loc[cpr, :].mean()
    plt.title("cpr = %d, std = %.2f" % (cpr, std_norm))
    plt.savefig(output_folder + f"/{cpr}")

# Conclusion:
# 0.05 should give a stable score (close to 1)
# 0.33 should also give a stable score (close to 1)
# 0.5 and higher should be unstable (close to 1)
