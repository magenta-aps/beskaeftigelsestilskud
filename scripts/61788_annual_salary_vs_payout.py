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

output_folder = os.environ["HOME"] + "/Pictures/plots/61666_payout_vs_salary"
functions.makedir(output_folder)


x = np.linspace(0, 800000, 300)

y = [functions.calculate(salary) for salary in x]

plt.figure(figsize=(18, 6))
plt.plot(x, y, lw=3)
plt.xlabel("Annual salary [kr]")
plt.ylabel("Total benefit [kr]")
plt.savefig(output_folder + "/salary_vs_payout")
