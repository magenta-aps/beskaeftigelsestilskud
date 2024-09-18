# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import os

import functions
import matplotlib.pyplot as plt
import pandas as pd

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

output_folder = os.environ["HOME"] + "/Pictures/plots/61666_stability_score_hist"
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()
df = df_a + df_b

df_stability_score = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df.columns if year in c]

    stability_score = df.loc[:, cols].apply(
        functions.calculate_stability_score, raw=True, axis=1
    )
    df_stability_score[year] = stability_score


percentage_with_stable_incomes = (
    (df_stability_score > 0.5).sum().sum() / df_stability_score.size * 100
)

plt.figure()
plt.hist(df_stability_score, label=df_stability_score.columns)
plt.xlabel("Stability score")
plt.ylabel("Amount of people")
plt.legend()
plt.title("Antal borgere med stabil indkomst: %.2f%%" % percentage_with_stable_incomes)
plt.savefig(output_folder + "/stability_score_histogram")
