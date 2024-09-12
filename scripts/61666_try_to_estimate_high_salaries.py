# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
#
# Hypothesis:
# - When we pay out too much it is because the person whom we are payout out for should
# have received NOTHING instead of the money that he/she received
# - A person is supposed to receive nothing when he/she earns over 500.000 in a year
#
# The challenge:
# - Can we use our stability score (or other metrics) to say already in Jan 2023 that a
# person is likely to earn over 500.000 in 2023?
#
# The available data:
# - Income data for 2020, 2021, 2022

import locale

import functions
import matplotlib.pyplot as plt
import pandas as pd

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

output_folder = "/home/nick/Pictures/plots/61666_estimate_high_salaries"
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()


df = df_a + df_b

df_annual = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df.columns if year in c]
    df_annual[year] = df.loc[:, cols].sum(axis=1)


I = df_annual.loc[:, "2023"] < (  # noqa: E741
    df_annual.loc[:, "2023"].mean() + df_annual.loc[:, "2023"].std() * 2
)
plt.figure()
plt.hist(df_annual.loc[I, "2023"])
plt.plot([500000, 500000], [0, 15000], "--", lw=3, label="500.000 limit")
plt.ylim(0, 15000)
plt.legend()
plt.xlabel("Annual salary 2023")
plt.ylabel("Amount of people")
plt.savefig(output_folder + "/salary_histogram")

df_data = df.loc[:, [c for c in df.columns if "2023" not in c]].fillna(0)
df_data_annual = df_annual.loc[:, ["2020", "2021", "2022"]]

# The goal is a set of True/False flags where True is we pay out and False is we do not
df_goal = df_annual.loc[:, "2023"]
I = df_data.mean(axis=1) > 0  # noqa: E741

# 1 = very stable
# 0 = very unstable
stability_score = df_data.apply(functions.calculate_stability_score, raw=True, axis=1)


# Stability score vs annual salary
plt.figure()
plt.plot(stability_score[I], df_goal[I], ".")
plt.plot([0, 1], [500_000, 500_000], "--", lw=3, label="500.000 limit")
plt.legend()
plt.xlim(0, 1)
plt.xlabel("Stability score [0-1]")
plt.ylabel("Annual salary [kr]")
plt.ylim(0, 4_000_000)
plt.savefig(output_folder + "/salary_vs_stability_score_of_past_years")


# Last years salary vs this years salary
plt.figure()
plt.plot(df_annual.loc[:, "2022"], df_annual.loc[:, "2023"], ".")
plt.plot([0, 4_000_000], [0, 4_000_000], "--")
plt.plot([0, 4_000_000], [500_000, 500_000], "--", lw=3, label="500.000 limit")

plt.xlim(0, 4_000_000)
plt.ylim(0, 4_000_000)
plt.legend()
plt.xlabel("Annual salary in 2022")
plt.ylabel("Annual salary in 2023")
plt.savefig(output_folder + "/salary_vs_last_year_salary")


locale.setlocale(locale.LC_ALL, "en_US.UTF-8")

# Plot some boundary salaries
I = (df_annual.loc[:, "2023"] > 400_000) & (  # noqa: E741
    df_annual.loc[:, "2023"] < 600_000
)
for cpr in df_annual.index[I][:50]:
    plt.figure(figsize=(18, 8))
    functions.plot_income(cpr, df_a, df_b)
    total_income = df_annual.loc[cpr, :]
    years = df_annual.columns
    total_income_str = [
        locale.format("%.2f", t, True) + f" ({y})" for t, y in zip(total_income, years)
    ]
    plt.title("Total income = \n" + "\n".join(total_income_str))
    plt.subplots_adjust(top=0.7)
    plt.savefig(output_folder + f"/medium_high_salary_timeseries_{cpr}")
