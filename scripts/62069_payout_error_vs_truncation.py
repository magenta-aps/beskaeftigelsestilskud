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

output_folder = (
    os.environ["HOME"] + "/Pictures/plots/62069_payout_error_vs_truncated_amount"
)
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()

# Test on first 1000 rows
# df_a = df_a.iloc[:100, :]
# df_b = df_b.iloc[:100, :]


df = df_a + df_b

df_annual_a = functions.calculate_annual_salary(df_a)
df_annual_b = functions.calculate_annual_salary(df_b)
df_annual = functions.calculate_annual_salary(df)


# %% Simulate InYearExtrapolationEngine to estimate incomes month-for-month
df_estimates = functions.estimate_annual_income(
    df_a,
    df_b,
    functions.in_year_engine,
    functions.in_year_engine,
)

# Validate that our simulations make sense
# by checking that we always estimate correctly in december
december_cols = [c for c in df.columns if "Dec" in c]
real_values_dec = df_annual.values.flatten()
estimated_values_dec = df_estimates.loc[:, december_cols].values.flatten()

plt.figure()
functions.scatter(real_values_dec, estimated_values_dec)
plt.xlabel("Real annual salary")
plt.ylabel("Estimated annual salary in december")
plt.savefig(output_folder + "/estimated_vs_real_salary_dec")

# Plot how good our estimates are
real_values = pd.Series()
estimated_values = pd.Series()
for col in df.columns:
    year = col.split("(")[1].split(")")[0]

    if len(real_values) > 0:
        real_values = pd.concat([real_values, df_annual.loc[:, year]])
        estimated_values = pd.concat([estimated_values, df_estimates.loc[:, col]])
    else:
        real_values = df_annual.loc[:, year]
        estimated_values = df_estimates.loc[:, col]


I = real_values < (real_values.mean() + real_values.std() * 2)
plt.figure()
functions.scatter(real_values[I], estimated_values[I])
plt.xlabel("Real annual salary")
plt.ylabel("Estimated annual salary")
plt.title("")
plt.savefig(output_folder + "/estimated_vs_real_salary")


# %% Calculate payout month-for-month
years = df_annual.columns
for truncate_amount in [0, 200]:
    df_payout, df_correct_payout = functions.calculate_payout(
        df_estimates,
        df_annual,
        truncate_amount=truncate_amount,
    )

    # Show payout-error
    df_errors = df_payout - df_correct_payout
    df_errors_annual = pd.DataFrame()
    for year in years:
        cols = [c for c in df_errors.columns if year in c]
        df_errors_annual[year] = df_errors.loc[:, cols].mean(axis=1)

    plt.figure()
    plt.hist(df_errors_annual, label=df_errors_annual.columns)
    plt.legend()
    plt.xlabel("Mean payout error [kr]")
    plt.ylabel("Amount of people")
    plt.title("truncate_amount = %dkr" % truncate_amount)
    plt.savefig(output_folder + f"/error_hist_truncate_{truncate_amount}_kr")

    tolerances = list(np.arange(0, 1000, 1))
    total_people = [
        (df_errors_annual < tolerance).sum().sum() / df_errors_annual.size * 100
        for tolerance in tolerances
    ]

    tolerance_to_highlight = 50
    amount_of_people_for_tolerance_to_highlight = total_people[
        tolerances.index(tolerance_to_highlight)
    ]

    plt.figure()
    plt.plot(tolerances, total_people, label="bagatel-grænse = %d" % truncate_amount)
    plt.ylabel("Amount of people\nfor whom we payout correctly")
    plt.xlabel("Tolerance [kr]")
    plt.title(
        "Andel af befolkning\nhvor vi udbetaler rigtigt (±%dkr): %.2f%%"
        % (tolerance_to_highlight, amount_of_people_for_tolerance_to_highlight)
    )
    plt.plot(
        [tolerance_to_highlight, tolerance_to_highlight],
        [0, amount_of_people_for_tolerance_to_highlight],
        "--",
        color="k",
    )

    plt.plot(
        [0, tolerance_to_highlight],
        [
            amount_of_people_for_tolerance_to_highlight,
            amount_of_people_for_tolerance_to_highlight,
        ],
        "--",
        color="k",
    )
    plt.xlim(0, max(tolerances))
    plt.ylim(40, max(total_people) * 1.2)
    plt.legend()
    plt.savefig(output_folder + f"/error_percentage_truncate_{truncate_amount}_kr")

# %% Conclusion
# We get 0.4% better at paying out if we only payout amounts over 200kr
