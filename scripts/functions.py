# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
def pltdefaults(bg="white", fontsize=12.0):
    import os

    import matplotlib as mpl
    from cycler import cycler

    mpl.rcParams["savefig.bbox"] = "standard"
    mpl.rcParams["axes.linewidth"] = 1
    mpl.rcParams["figure.figsize"] = 8, 5
    if os.name != "nt":
        mpl.rcParams["font.family"] = "DejaVu Sans"
    else:
        mpl.rcParams["font.family"] = "Arial"
    mpl.rcParams["font.weight"] = "bold"
    mpl.rcParams["axes.labelweight"] = "bold"
    mpl.rcParams["axes.grid"] = True
    mpl.rcParams["grid.linestyle"] = "-"
    mpl.rcParams["grid.linewidth"] = 1
    mpl.rcParams["axes.axisbelow"] = True
    mpl.rcParams["font.size"] = fontsize
    mpl.rcParams["axes.titlesize"] = "x-large"
    mpl.rcParams["axes.titleweight"] = "bold"
    mpl.rcParams["figure.titleweight"] = "bold"
    mpl.rcParams["figure.titlesize"] = "xx-large"
    mpl.rcParams["axes.labelsize"] = "large"
    mpl.rcParams["figure.subplot.top"] = 0.85
    mpl.rcParams["figure.subplot.bottom"] = 0.13

    mpl.rcParams["grid.alpha"] = 0.4
    mpl.rcParams["grid.linewidth"] = 0.2

    mpl.rcParams["axes.xmargin"] = 0.05
    mpl.rcParams["axes.ymargin"] = 0.05

    mpl.rcParams["xtick.minor.visible"] = True
    mpl.rcParams["axes.grid.which"] = "both"

    mpl.rcParams["axes.labelpad"] = 8
    mpl.rcParams["patch.force_edgecolor"] = True
    mpl.rcParams["figure.max_open_warning"] = 300

    mpl.rcParams["axes.prop_cycle"] = cycler(
        "color",
        [
            "#CC00CC",
            "#6C244C",
            "#1f77b4",
            "#ff7f0e",
            "#2ca02c",
            "#d62728",
            "#9467bd",
            "#8c564b",
            "#e377c2",
            "#7f7f7f",
            "#bcbd22",
            "#17becf",
        ],
    )


def load_data():
    """
    Loads income data

    Example
    ----------
    >>> import functions
    >>> df_a, df_b = functions.load_data()


    Returns
    ------------
    df_a : pd.DataFrame
        Dataframe with a-income. Indexed on CPR number
    df_b : pd.DataFrame
        Dataframe with b-income. Indexed on CPR number
    """
    import os

    import pandas as pd

    dfs = [pd.DataFrame(), pd.DataFrame()]

    for year in [2020, 2021, 2022, 2023]:
        file = f"a_og_b_{year}.csv"
        df = pd.read_csv(os.path.join("../bf", file), sep=",")
        df = df.groupby(df.CPR).sum()
        df.columns = [c + f" ({year})" for c in df.columns]

        for col in df.columns:
            if "a-indkomst" in col:
                dfs[0][col.replace("a-indkomst ", "")] = df.loc[:, col]
            elif "indh.-indkomst" in col:
                dfs[1][col.replace("indh.-indkomst ", "")] = df.loc[:, col]

    return dfs


def plot_income(cpr, df_a, df_b):
    import matplotlib.pyplot as plt

    # Sum A and B income
    df = df_a + df_b

    plt.bar(df.columns, df.loc[cpr, :], label="A+B", color="#6C244C")
    plt.bar(df_a.columns, df_a.loc[cpr, :], label="A", color="#CC00CC")
    plt.xticks(rotation=90)
    plt.subplots_adjust(bottom=0.3)
    plt.ylabel("Income [kr]")
    plt.title(f"CPR = {cpr}")
    plt.legend()


def map_between_zero_and_one(std, s=0.2, k=1.5):
    import numpy as np

    return 1 - np.exp(-(std**k) / s**k)


def calculate_stability_score(values):
    import numpy as np

    # Normalize data
    values_norm = values / np.mean(values)

    # Calculate variance
    std = np.std(values_norm)

    # Map between 0 and 1
    # https://math.stackexchange.com/questions/2833062/a-measure-similar-to-
    # variance-thats-always-between-0-and-1
    return map_between_zero_and_one(std)


def makedir(Path):
    """
    Makes a new directory at specified path location, if it does not exist yet
    """
    import os

    if not os.path.exists(Path):
        os.makedirs(Path)
