# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import functions
import matplotlib
import pandas as pd

matplotlib.use("Agg")  # Agg does not display the plots on-screen.

import matplotlib.pyplot as plt  # noqa: E402

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

# Load data
df_a, df_b = functions.load_data()

# Plot the results
n = len(df_a)
for counter, cpr in enumerate(df_a.index):
    print(f"{counter+1}/{n}")
    plt.figure(figsize=(20, 8))
    functions.plot_income(cpr, df_a, df_b)
    plt.savefig(f"figures/61788_income_plots/{cpr}")
    plt.close()
