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

output_folder = os.environ["HOME"] + "/Pictures/plots/62855_quarantine_ladder"
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()
df = df_a + df_b

df_annual_a = functions.calculate_annual_salary(df_a)
df_annual_b = functions.calculate_annual_salary(df_b)
df_annual = functions.calculate_annual_salary(df)

df_annual_std = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df.columns if year in c]
    df_annual_std[year] = df.loc[:, cols].std(axis=1)

df_upper = df_annual + df_annual_std
df_lower = df_annual - df_annual_std


avg_std = df_annual_std.mean().mean()

quarantine_limit = 500000 - avg_std
x = np.linspace(0, 800000, 3000)

y = [functions.calculate_benefit(salary) for salary in x]
y = []
for salary in x:
    benefit = functions.calculate_benefit(salary) if salary < quarantine_limit else 0
    y.append(benefit / 12)

percentage_in_quarantine = (
    ((df_upper > 500000) & (df_annual <= 500000)).sum() / len(df)
).mean() * 100

plt.figure(figsize=(18, 6))
plt.plot(x, y, lw=3)
plt.xlabel("Annual salary [kr]")
plt.ylabel("Monthly benefit [kr]")
plt.title("Percentage of people in quarantine: %.2f%%" % percentage_in_quarantine)
plt.savefig(output_folder + "/salary_vs_payout")

f = open(output_folder + "/ladder.txt", "w")
for salary in np.arange(0, 600000, step=10000):
    benefit = np.interp(salary, x, y)
    actual_benefit = functions.calculate_benefit(salary)
    ladder_string = "- Når man tjener %d kr/år får man %d kr/måned" % (salary, benefit)

    if benefit == 0 and salary < 500000 and salary > 400000:
        ladder_string += " (Man får dog %d kr i december)" % actual_benefit

    ladder_string += "\n"

    print(ladder_string)
    f.write(ladder_string)
f.close()
