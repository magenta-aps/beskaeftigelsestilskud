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

    file_path = os.path.dirname(os.path.realpath(__file__))
    dfs = [pd.DataFrame(), pd.DataFrame()]

    for year in [2020, 2021, 2022, 2023]:
        file = f"a_og_b_{year}.csv"
        df = pd.read_csv(os.path.join(file_path, "../bf/data", file), sep=",")
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


def map_between_zero_and_one(std, s=0.4, k=2.5):
    import numpy as np

    return np.exp(-(std**k) / s**k)


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


def calculate_benefit(
    amount,
    benefit_rate_percent=17.5,
    personal_allowance=58000,
    standard_allowance=10000,
    max_benefit=15750,
    scaledown_rate_percent=6.3,
    scaledown_ceiling=250000,
):

    zero = 0
    benefit_rate = benefit_rate_percent * 0.01
    scaledown_rate = scaledown_rate_percent * 0.01
    rateable_amount = max(amount - personal_allowance - standard_allowance, zero)
    scaledown_amount = max(amount - scaledown_ceiling, zero)
    return round(
        max(
            min(benefit_rate * rateable_amount, max_benefit)
            - scaledown_rate * scaledown_amount,
            zero,
        ),
        2,
    )


def calculate_annual_salary(df):
    import pandas as pd

    df_annual = pd.DataFrame()
    for year in ["2020", "2021", "2022", "2023"]:
        cols = [c for c in df.columns if year in c]
        df_annual[year] = df.loc[:, cols].sum(axis=1)

    return df_annual


def __ODR_fit(x, y, func):
    # Subfunction for ODR fits
    import scipy.odr

    # Linear model
    linear = scipy.odr.Model(func)

    # Data
    mydata = scipy.odr.Data(x, y)

    # ODR model
    myodr = scipy.odr.ODR(mydata, linear, beta0=[1.0, 2.0])

    # Run the model
    myoutput = myodr.run()

    return myoutput.beta


def scatter(
    x,
    y,
    label_add="",
    plot=True,
    conf_int=False,
    zorder=[0, 1],
    w=None,
    infer_labels=True,
    markersize=None,
    legend_fontsize=13,
    fit_to_plot=0,
    ax=None,
    ODR=False,
    add_one_to_one=True,
    legend_loc=2,
):
    """
    Plot xy plot and best least-squares fit.

    Parameters
    ----------
    x : array
        x values, in a dataframe or series
    y : array
        y values, in a dataframe or series

    Returns
    ----------
    m : float
        slope of y=mx+b fit
    b : float
        offset of y=mx+b fit
    slope : float
        slope of y=mx fit
    offset : float
        offset of y=x+b fit
    R2 : float
        Correlation coefficient
    counter : float
        Number of data points

    Other Parameters
    -----------------
    label_add : string
        Text to add to the label of the legend
    plot : bool
        To plot (True) or not to plot (False) default = True
    conf_int : bool
        False for least squares regression, True for OSL with confidence bounds
        In this case, no 'slope' and 'offset' are returned
    zorder : number
        Zorder of the scatter points [0] and plotted line [1]
    infer_labels : Boolean
        If True, will try to set the x, y and title labels automatically with the
        series names.
        Note: Only works if input arrays are pandas Series.
    w : array_like
        Weights to apply to the y-coordinates of the sample points. For gaussian
        uncertainties, use 1/sigma (not 1/sigma**2)
    markersize : float
        Marker size of points
    fit_to_plot : int
        Set this to a number,
        to plot a different fit:

            * 0: Plots the y=ax+b fit
            * 1: Plots the y=ax+0 fit
            * 2: Plots the y=x+b fit
    ax : Axes
        Axes to plot on
    ODR : Boolean
        Set this to True to do Orthogonal Distance Regression (ODR) instead of
        regular least-squares regression.
    add_one_to_one : Boolean
        Set this to True to add a thin grey line showing where the 1:1 lies
    legend_loc : int
        loc of the legend. 2 = left-upper corner

    Notes
    ----------
    conf_int = True will give slightly different Rsquared value.

    Examples
    ----------
    For an iSpin wind speed U_iSpin and met-mast wind speed U_MM, the scatter
    plot, and linear least-squares fits, can be made using:

    >>> plt.figure()
    >>> functions.scatter(x,y)

    You can also just retrieve the fitted coefficients, without making a plot

    >>> m,b,slope, offset,R2,counter=functions.scatter(x,y,plot=False)

    """
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    # ODR function: y=x*m+b
    def odr_func_linfit(B, x):
        return B[0] * x + B[1]

    # ODR function: y=x+b
    def odr_func_linfit_s1(B, x):
        return x + B[1]

    # ODR function: y=x*m
    def odr_func_linfit_o0(B, x):
        return B[0] * x

    def plot_one_to_one():
        xlim = plt.gca().get_xlim()
        ylim = plt.gca().get_ylim()

        min_val = np.min([xlim[0], ylim[0]])
        max_val = np.max([xlim[1], ylim[1]])

        plt.plot(
            [min_val, max_val],
            [min_val, max_val],
            "-",
            color="grey",
            zorder=0,
            alpha=0.5,
            lw=0.5,
        )
        plt.xlim(xlim)
        plt.ylim(ylim)

    if label_add != "":
        label_add = "\n" + label_add

    if ax is not None:
        active_ax = plt.gca()
        plt.sca(ax)

    # First method: Least squares regression.
    if conf_int == 0:
        # Fit with offset forced to zero
        def fitlin(xdata, ydata):
            from scipy.optimize import curve_fit

            def linfunc(x, p1):
                return p1 * x

            popt, pcov = curve_fit(linfunc, xdata, ydata, p0=(0.5))
            return popt[0]

        # Fit with slope forced to one
        def fitlin2(xdata, ydata):
            from scipy.optimize import curve_fit

            def linfunc(x, p1):
                return 1 * x + p1

            popt, pcov = curve_fit(linfunc, xdata, ydata, p0=(0.5))
            return popt[0]

        # Remove nans
        I = ~np.isnan(x) & ~np.isnan(y)  # noqa: E741

        if (w is None) is False:
            w = w[I]

        # Slope and offset
        if ODR:
            m, b = __ODR_fit(x[I], y[I], odr_func_linfit)
        else:
            m, b = np.polyfit(x[I], y[I], 1, w=w)

        # Slope and offset, where either one is fixed
        if w is None:
            if ODR:
                slope = __ODR_fit(x[I], y[I], odr_func_linfit_o0)[0]
                offset = __ODR_fit(x[I], y[I], odr_func_linfit_s1)[0]
            else:
                slope = fitlin(x[I], y[I])
                offset = fitlin2(x[I], y[I])
        else:
            slope = np.nan
            offset = np.nan
        # Range of x values
        if type(x) is pd.core.series.Series:
            try:
                xr = np.linspace(np.nanmin(x).values[0], np.nanmax(x).values[0])
            except:  # noqa: E722
                xr = np.linspace(np.nanmin(x), np.nanmax(x))
        else:
            xr = np.linspace(np.nanmin(x), np.nanmax(x))
        # Correlation coefficient
        R2 = np.corrcoef(x[I], y[I])[1][0]
        # number of datapoints
        counter = np.sum(~np.isnan(x) & ~np.isnan(y))
        if plot == 1:
            if isinstance(zorder, (int, float)):
                zorder = [zorder, zorder]
            plt.plot(x, y, ".", label="", zorder=zorder[0], markersize=markersize)
            if fit_to_plot == 0:
                plt.plot(
                    xr,
                    xr * m + b,
                    lw=3,
                    label="y = {:+.3f}x {:+.3f}".format(m, b),
                    zorder=zorder[1],
                )
                plt.plot(
                    [],
                    [],
                    ".",
                    ms=0,
                    label=(
                        "y = {:+.3f}x\ny = x {:+.3f}\n{:s} = {:.2%}\nn = {:.0f}"
                    ).format(slope, offset, r"$R^2$", R2, counter)
                    + label_add,
                )
            elif fit_to_plot == 1:
                plt.plot(
                    xr,
                    xr * slope,
                    lw=3,
                    label="y = {:+.3f}x".format(slope),
                    zorder=zorder[1],
                )
                plt.plot(
                    [],
                    [],
                    ".",
                    ms=0,
                    label=(
                        "y = {:+.3f}x {:+.3f}\n"
                        "y = x {:+.3f} \n{:s} = {:.2%}\nn = {:.0f}"
                    ).format(m, b, offset, r"$R^2$", R2, counter)
                    + label_add,
                )
            elif fit_to_plot == 2:
                plt.plot(
                    xr,
                    xr + offset,
                    lw=3,
                    label="y = x {:+.3f}".format(offset),
                    zorder=zorder[1],
                )
                plt.plot(
                    [],
                    [],
                    ".",
                    ms=0,
                    label=(
                        "y = {:+.3f}x\ny = {:+.3f}x {:+.3f}{:s} = {:.2%}\nn = {:.0f}"
                    ).format(slope, m, b, r"$R^2$", R2, counter)
                    + label_add,
                )
            plt.legend(loc=legend_loc, framealpha=0.9, fontsize=legend_fontsize)

            #            import pandas as pd
            if (
                (type(x) is pd.core.series.Series)
                & (type(y) is pd.core.series.Series)
                & infer_labels
            ):
                plt.xlabel(x.name)
                plt.ylabel(y.name)
                plt.title("%s vs. %s" % (x.name, y.name))

        if add_one_to_one:
            plot_one_to_one()

        if ax is not None:
            plt.sca(active_ax)

        return m, b, slope, offset, R2, counter


def in_year_engine(values_this_year):
    """
    InYearExtrapolationEngine

    Parameters
    ------------
    values_this_year: list
        Income values for a given year

    Returns
    ---------
    estimate : float
        Estimated annual salary
    """
    import numpy as np

    return np.sum(values_this_year) / len(values_this_year) * 12


def get_cols_for_year(df, year):
    """
    Returns
    --------
    cols: list
        Columns for a given year.

    """
    return [c for c in df.columns if year in c]


def get_year_from_col_label(col):
    """
    Examples
    -----------
    >>> year = get_year_from_col_label("Sep (2023)")
    >>> year
    >>> "2023"
    """

    return col.split("(")[1].split(")")[0]


def get_month_from_col_label(col):
    """
    Examples
    -----------
    >>> year = get_month_from_col_label("Sep (2023)")
    >>> year
    >>> "Sep"
    """

    return col.split(" ")[0]


def estimate_annual_income(df_a, df_b, estimation_engine_a, estimation_engine_b):
    """
    Estimates annual A and B income

    Parameters
    --------------
    df_a: DataFrame
        Dataframe with A-income - indexed on cpr no. Every column is a month
    df_b: DataFrame
        Dataframe with B-income - indexed on cpr no. Every column is a month
    estimation_engine_a : function
        Estimation engine to use for A-income. For example functions.in_year_engine
    estimation_engine_b : function
        Estimation engine to use for B-income. For example functions.in_year_engine

    """
    import numpy as np
    import pandas as pd

    years = sorted(np.unique([get_year_from_col_label(c) for c in df_a.columns]))

    df_a_estimates_list = [
        df_a.loc[:, get_cols_for_year(df_a, year)]
        .T.rolling(12, min_periods=1)
        .apply(estimation_engine_a)
        .T
        for year in years
    ]
    df_b_estimates_list = [
        df_b.loc[:, get_cols_for_year(df_b, year)]
        .T.rolling(12, min_periods=1)
        .apply(estimation_engine_b)
        .T
        for year in years
    ]

    df_a_estimates = pd.concat(df_a_estimates_list, axis=1)
    df_b_estimates = pd.concat(df_b_estimates_list, axis=1)

    df_estimates = df_a_estimates + df_b_estimates
    return df_estimates


def calculate_payout(df_estimates, df_annual, treshold=0.05, truncate_amount=0):
    """
    Calculate payout given a set of estimates

    Parameters
    ---------------
    df_estimates : DataFrame
        Dataframe with estimates. Indexed by CPR number and every column is a
        yearly-salary-estimate.
    df_annual: DataFrame
        Dataframe with actual annual salary. Indexed by CPR number and every column
        is a year
    """
    import pandas as pd

    months = [get_month_from_col_label(c) for c in df_estimates.columns][:12]
    years = df_annual.columns
    df_payout = pd.DataFrame(
        index=df_estimates.index,
        columns=df_estimates.columns,
    ).astype(float)
    df_correct_payout = df_payout.copy()

    for year in years:
        for month in months:
            this_month = f"{month} ({year})"

            month_index = months.index(month)
            if month_index > 0:
                last_month = f"{months[month_index-1]} ({year})"
            else:
                last_month = None

            past_months = [f"{m} ({year})" for m in months[:month_index]]

            estimated_year_benefit = df_estimates.loc[:, this_month].map(
                calculate_benefit
            )
            actual_year_benefit = df_annual.loc[:, year].map(calculate_benefit)

            prior_months = df_payout.loc[:, past_months]
            prior_benefit_paid = prior_months.sum(axis=1)
            benefit_this_month = (estimated_year_benefit - prior_benefit_paid) / (
                12 - month_index
            )
            actual_benefit_this_month = actual_year_benefit / 12

            if month_index != 11:
                benefit_this_month[benefit_this_month < truncate_amount] = 0
            benefit_this_month[benefit_this_month < 0] = 0

            if last_month:
                benefit_last_month = df_payout.loc[:, last_month]

                diff = pd.Series(index=benefit_last_month.index)
                I_diff = benefit_last_month > 0
                diff_abs = (benefit_this_month - benefit_last_month).abs()
                diff[I_diff] = diff_abs[I_diff] / benefit_last_month[I_diff]

                small_diffs = diff < treshold
                benefit_this_month[small_diffs] = benefit_last_month[small_diffs]

            df_payout.loc[:, this_month] = benefit_this_month
            df_correct_payout.loc[:, this_month] = actual_benefit_this_month
    return df_payout, df_correct_payout
