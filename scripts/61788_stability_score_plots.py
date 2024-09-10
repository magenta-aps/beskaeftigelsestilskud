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

output_folder = "/home/nick/Pictures/plots/61788_stability_score"
functions.makedir(output_folder)
functions.makedir(output_folder + "/stable_incomes")
functions.makedir(output_folder + "/mixed_incomes")
functions.makedir(output_folder + "/unstable_incomes")

# Load data
df_a, df_b = functions.load_data()

df_a = df_a.iloc[:10000, :]
df_b = df_b.iloc[:10000, :]

# 12-month rolling sum (i.e. TwelveMonthsSummationEngine)
df_a_estimates = df_a.T.rolling(12).sum().T

# Real yearly salary
df_a_real = pd.DataFrame(index=df_a.index, columns=df_a.columns)

for year in [2020, 2021, 2022, 2023]:
    december_col = f"Dec ({year})"
    for col in df_a_real.columns:
        if str(year) in col:
            df_a_real.loc[:, col] = df_a_estimates.loc[:, december_col]

# %% Plot results
df = df_a + df_b
s = 0.2
k = 1.5

df_ss_a = df_a.T.rolling(12).apply(functions.calculate_stability_score, raw=True).T
df_ss_b = df_b.T.rolling(12).apply(functions.calculate_stability_score, raw=True).T
df_std = df_a.T.rolling(12).std().T / df_a.T.rolling(12).mean().T

for cpr in list(df.index):
    print(cpr)
    fig, [(ax1, ax2), (ax3, ax4)] = plt.subplots(2, 2, sharex=True, figsize=(22, 14))
    plt.subplots_adjust(left=0.05)

    ax1.bar(df.columns, df.loc[cpr, :], label="A+B", color="#6C244C")
    ax1.bar(df_a.columns, df_a.loc[cpr, :], label="A", color="#CC00CC")
    ax1.set_ylabel("Income [kr]")
    ax1.set_title(f"CPR = {cpr}")
    ax1.legend()

    ax2.plot(df_a_real.loc[cpr, :], label="Yearly income (real)", lw=3)
    ax2.plot(df_a_estimates.loc[cpr, :], "--", label="Yearly income (estimate)", lw=2)
    ax2.legend()

    ax3.plot(df_ss_a.loc[cpr, :], lw=3, label="A")
    ax3.plot(df_ss_b.loc[cpr, :], lw=3, label="B")
    ax3.set_title("Stability score")
    ax3.set_ylim(0, 1.1)
    ax3.legend()

    ax4.plot(df_std.loc[cpr, :], lw=3)
    ax4.set_title("Standard dev (Normalized)")

    ax4.tick_params(axis="x", labelrotation=90)
    ax3.tick_params(axis="x", labelrotation=90)

    max_score = df_ss_a.loc[cpr, :].max()
    min_score = df_ss_a.loc[cpr, :].min()
    if max_score <= 0.5:
        plt.savefig(output_folder + f"/stable_incomes/{cpr}")
    elif max_score > 0.5 and min_score <= 0.5:
        plt.savefig(output_folder + f"/mixed_incomes/{cpr}")
    else:
        plt.savefig(output_folder + f"/unstable_incomes/{cpr}")

    plt.close()
