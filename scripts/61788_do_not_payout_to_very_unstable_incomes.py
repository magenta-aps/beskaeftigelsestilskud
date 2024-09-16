# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

# Men hvad nu, hvis vi sagde, at vi gerne vil udelukke de mest ustabile
# indtægter? For eksempel: Lad os sige, at vi vedtager ikke at udbetale
# til folk med en stabilitetsscore under en bestemt grænse.

# Hvor mange ville vi så udelukke, som skulle have haft, og hvor mange vil vi
# sikre, at vi ikke udbetaler for meget til?
import os

import functions
import matplotlib.pyplot as plt
import pandas as pd

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

output_folder = (
    os.environ["HOME"] + "/Pictures/plots/61666_do_not_payout_unstable_incomes"
)
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()
df = df_a + df_b

df_annual = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df.columns if year in c]
    df_annual[year] = df.loc[:, cols].sum(axis=1)


df_data = df.loc[:, [c for c in df.columns if "2023" not in c]].fillna(0)
df_data_annual = df_annual.loc[:, ["2020", "2021", "2022"]]

# The goal is a set of True/False flags where True is we pay out and False is we do not
df_goal = df_annual.loc[:, "2023"]
I = df_data.mean(axis=1) > 0  # noqa: E741

# 1 = very stable
# 0 = very unstable
stability_score = df_data.apply(functions.calculate_stability_score, raw=True, axis=1)

cols_2022 = [c for c in df_data.columns if "2022" in c]
stability_score_2022 = df_data.loc[:, cols_2022].apply(
    functions.calculate_stability_score, raw=True, axis=1
)


# Stability score vs annual salary
plt.figure(figsize=(14, 6))
plt.plot(stability_score_2022[I], df_goal[I], ".")
plt.plot([0, 1], [500_000, 500_000], "--", lw=3, label="500.000 limit")
plt.legend()
plt.xlim(0, 1)
plt.xlabel("Stability score i 2022 [0-1]")
plt.ylabel("Annual salary i 2023 [kr]")
plt.ylim(0, 4_000_000)


# Amount of people with highly unstable incomes and who should get payout
I = (  # noqa: E741
    (df_annual.loc[:, "2023"] < 500_000)
    & (df_annual.loc[:, "2023"] > 75_000)
    & (stability_score_2022 < 0.2)
)

percentage = sum(I) / len(df_annual) * 100

plt.title(
    ("Amount of people with unstable income who should get a payout:\n%.2f%%")
    % percentage
)

plt.plot(
    stability_score_2022[I],
    df_goal[I],
    ".",
    label="ustabile indkomster som skal have udbetaling",
)
plt.legend()

plt.savefig(output_folder + "/salary_vs_stability_score_of_past_years")
