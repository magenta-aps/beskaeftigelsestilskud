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
    os.environ["HOME"] + "/Pictures/plots/62259_payout_error_with_quarantine"
)
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()

# Test on first 1000 rows
# df_a = df_a.iloc[:1000, :]
# df_b = df_b.iloc[:1000, :]


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
for quarantine_amount in [0, 100, 500]:
    df_payout, df_correct_payout = functions.calculate_payout(
        df_estimates,
        df_annual,
        truncate_amount=100,
    )

    # Show payout-error
    df_errors = df_payout - df_correct_payout
    df_errors_annual = pd.DataFrame()
    for year in years:
        cols = [c for c in df_errors.columns if year in c]
        df_errors_annual[year] = df_errors.loc[:, cols].mean(axis=1)

    number_of_people_in_quarantine = 0

    if quarantine_amount:
        for year in years:
            if year > years[0]:
                I_quarantine = df_errors_annual[str(int(year) - 1)] > quarantine_amount

                # When a citizen is in quarantine we always pay out correctly
                # Because the payout does not come before december
                df_errors_annual.loc[I_quarantine, year] = 0
                number_of_people_in_quarantine += sum(I_quarantine)

    number_of_people_in_quarantine_p = (
        number_of_people_in_quarantine / (len(years) - 1) / len(df) * 100
    )

    plt.figure()
    plt.hist(df_errors_annual, label=df_errors_annual.columns)
    plt.legend()
    plt.xlabel("Mean payout error [kr]")
    plt.ylabel("Amount of people")
    plt.title(
        "quarantine_amount = %dkr\nNumber of people in quarantine: %d (%.1f%%)"
        % (
            quarantine_amount,
            number_of_people_in_quarantine,
            number_of_people_in_quarantine_p,
        )
    )
    plt.savefig(output_folder + f"/error_hist_quarantine_{quarantine_amount}_kr")

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
    plt.plot(
        tolerances, total_people, label="quarantine_amount = %d" % quarantine_amount
    )
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
    plt.savefig(output_folder + f"/error_percentage_quarantine_{quarantine_amount}_kr")

# %% Conclusion
# We get 3.72% better at paying out if we put people in quaraintaine when we overpay
# by 100kr
#
# That also means that 3.72% of the population will need to wait for their payout until
# December
#
# When we quarantine people when overpaying by 500kr we only affect 0.27% of the
# population, but we also only get 0.27% better at paying out...
#
# With a 100kr-quarantine rule about 10% of the population is in quaraintaine.
# With a 500kr-quarantine rule about 0.6% of the population is in quaraintaine.
