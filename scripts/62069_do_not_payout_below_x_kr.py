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

output_folder = os.environ["HOME"] + "/Pictures/plots/62069_no_payout_below_x_kr"
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()
df = df_a + df_b

# Calculate how much benefit everyone gets
df_annual = functions.calculate_annual_salary(df)
df_benefit = df_annual.map(functions.calculate)
df_benefit_monthly = df_benefit / 12


# Now calculate how many people would not get if we would refuse to pay out amounts
# lower than "x"
lower_borders = np.linspace(1, 300, 1000)
amount_of_people = [
    sum((df_benefit_monthly["2023"] < x) & (df_benefit_monthly["2023"] > 0))
    for x in lower_borders
]

N = sum(df_benefit_monthly["2023"] > 0)
amount_of_people_p = [a / N * 100 for a in amount_of_people]


I = df_benefit_monthly["2023"] > 0  # noqa: E741

plt.figure()
plt.hist(df_benefit_monthly["2023"][I])
plt.xlabel("Beskæftigelsestilskud / måned")
plt.ylabel("Antal personer [-]")
plt.savefig(output_folder + "/besk_hist")

plt.figure()
plt.plot(lower_borders, amount_of_people_p, lw=3)
plt.xlabel("Månedlige Bagatel-grænse [kr]")
plt.ylabel("Antal personer som vi rammer [%]")
plt.title(
    "Antal personer som vi IKKE udbetaler til \n(som ellers ville have fået noget)"
)
plt.savefig(output_folder + "/payout_limit_vs_amount_of_people")

# Conclusion:
# About 8% of the population would be affected by lower payout limit of 200kr.
