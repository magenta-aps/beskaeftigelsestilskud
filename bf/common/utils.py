# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import re
from typing import TypeVar
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import numpy as np
import pandas as pd
from django.conf import settings
from django.db.models import QuerySet
from django.utils.translation import gettext_lazy as _
from more_itertools import one

from bf.estimation import EstimationEngine, SameAsLastMonthEngine
from bf.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyAIncomeReport,
    MonthlyBIncomeReport,
    PersonMonth,
    PersonYear,
    Year,
)

pd.set_option("future.no_silent_downcasting", True)


def add_parameters_to_url(url: str, keys_to_add: dict) -> str:
    u = urlparse(url)
    query = parse_qs(u.query, keep_blank_values=True)
    for key, value in keys_to_add.items():
        query[key] = [str(value)]
    u = u._replace(query=urlencode(query, True))
    return urlunparse(u)


def map_between_zero_and_one(std: float, s=0.4, k=2.5) -> float:
    """
    Maps a value between zero and one

    Parameters
    --------------
    std: float
        Normalized standard deviation

    Other parameters
    s: float
        Parameter to adjust how fast we converge to 1
    k: float
        Parameter to adjust how fast we converge to 1

    References
    -------------
    [1] https://math.stackexchange.com/questions/2833062/a-measure-similar-to-
    variance-thats-always-between-0-and-1

    """
    return np.exp(-(std**k) / s**k)


def calculate_stability_score(values: list, s=0.4, k=2.5) -> float:
    """
    Calculates stability score - 1 represents a stable income and 0 is unstable

    Parameters
    -------------
    values: list
        List of monthly income values in [kr]
    """
    # Calculate average income
    mean = np.nanmean(values)

    # No income is a stable income
    if mean == 0:
        return 1

    # Normalize data
    values_norm = values / mean

    # Calculate variance
    std = np.nanstd(values_norm)

    # Map between 0 and 1
    return map_between_zero_and_one(std, s=s, k=k)


def to_dataframe(qs: QuerySet, index: str, dtypes: dict) -> pd.DataFrame:
    """
    Converts queryset to dataframe

    Parameters
    -------------
    qs: QuerySet
        Queryset to convert to dataframe
    index: str
        Field to use as index
    dtypes: dict
        Dictionary with values and their types

    Returns
    ----------
    Dataframe indexed in "index" and with a column for every entry in the dtypes dict
    """
    columns = list(dtypes.keys()) + [index]
    df = pd.DataFrame(list(qs.values_list(*columns)), columns=columns)
    df = df.set_index(index)
    df = df.astype(dtypes)
    return df.rename({c: c.split("__")[-1] for c in columns}, axis=1)


def get_income_as_dataframe(year: int, cpr_numbers: list = []) -> dict:
    """
    Loads income for an entire year

    Parameters
    ---------------
    year: int
        Year to return income data for

    Returns
    -----------
    output_dict: dictionary
        Dict with two keys ("A" and "B") and two dataframes. Dataframes
        are indexed by CPR-number and every column represents a month
    """
    a_income_qs = MonthlyAIncomeReport.objects.filter(year=year)
    b_income_qs = MonthlyBIncomeReport.objects.filter(year=year)

    if cpr_numbers:
        a_income_qs = a_income_qs.filter(person__cpr__in=cpr_numbers)
        b_income_qs = b_income_qs.filter(person__cpr__in=cpr_numbers)

    output_dict = {}
    for qs, income_type in zip([a_income_qs, b_income_qs], IncomeType):

        df = to_dataframe(
            qs=qs,
            index="person__cpr",
            dtypes={"amount": float, "month": int},
        )

        output_dict[income_type] = df.pivot_table(
            values="amount",
            index=df.index,
            columns="month",
            aggfunc="sum",
        )
    return output_dict


def calculate_stability_score_for_entire_year(year: int) -> pd.DataFrame:
    """
    Calculates stability score for all people in a given year

    Parameters
    ---------------
    year: int
        Year to return income data for

    Returns
    -----------
    df_stability_score: DataFrame
        Dataframe with income data. Indexed by cpr-number.
        Two columns, one for A and one for B income
    """
    income_dict = get_income_as_dataframe(year)

    df_stability_score = pd.DataFrame()
    for income_type, df_income in income_dict.items():
        df_stability_score[income_type] = df_income.apply(
            calculate_stability_score,
            axis=1,
            raw=True,
        )

    return df_stability_score


def get_income_estimates_df(
    month: int,
    year: int,
    cpr: str | None = None,
    engine_a: str | None = None,
    engine_b: str | None = None,
) -> pd.DataFrame:
    """
    Get income estimates as dataframe

    Parameters
    --------------
    month: int
        Month to return income estimates for
    year: int
        Year to return income estimates for

    Other parameters
    ------------------
    cpr: str
        Person to return income estimates for

    Returns
    ----------
    df: DataFrame
        Dataframe with income estimates. Indexed on cpr number. Contains a column for
        "estimated_year_result" and one for "actual_year_result"
    """
    estimates_qs = IncomeEstimate.objects.filter(
        person_month__month=month,
        person_month__person_year__year__year=year,
    )

    if cpr:
        estimates_qs = estimates_qs.filter(person_month__person_year__person__cpr=cpr)

    df = to_dataframe(
        estimates_qs,
        index="person_month__person_year__person__cpr",
        dtypes={
            "engine": str,
            "person_month__person_year__preferred_estimation_engine_a": str,
            "person_month__person_year__preferred_estimation_engine_b": str,
            "income_type": str,
            "estimated_year_result": float,
            "actual_year_result": float,
        },
    )

    engine_dict: dict = {}
    for income_type in IncomeType:
        if income_type == IncomeType.A and engine_a:
            engine_dict[income_type] = engine_a
        elif income_type == IncomeType.B and engine_b:
            engine_dict[income_type] = engine_b
        else:
            engine_dict[income_type] = df.loc[
                :, f"preferred_estimation_engine_{income_type.lower()}"
            ]

    estimates_dfs = {}
    for income_type in IncomeType:
        estimates_dfs[income_type] = df.loc[
            (df.engine == engine_dict[income_type]) & (df.income_type == income_type),
            ["estimated_year_result", "actual_year_result"],
        ]

    return estimates_dfs[IncomeType.A] + estimates_dfs[IncomeType.B]


def get_payout_df(month: int, year: int, cpr: str | None = None) -> pd.DataFrame:
    """
    Return dataframe with all payouts up to the indicated month

    Parameters
    --------------
    month: int
        Month to return payouts for. Payouts for all months before this month will be
        returned
    year: int
        Year to return payouts for.

    Other parameters
    ------------------
    cpr: str
        Person to return payouts for

    Returns
    ------------
    df: DataFrame
        Dataframe with payouts. Indexed by CPR number. Every column is a monthly payout.

    Notes
    -------
    The "benefit_paid_month_0" column corresponds to December of the previous year.

    """
    month_this_year_qs = PersonMonth.objects.filter(
        person_year__year__year=year, month__lt=month
    )
    month_last_year_qs = PersonMonth.objects.filter(
        person_year__year__year=year - 1, month=12
    )

    dfs = []
    for month_qs in [month_last_year_qs, month_this_year_qs]:
        month_df = to_dataframe(
            month_qs.filter(person_year__person__cpr=cpr) if cpr else month_qs,
            index="person_year__person__cpr",
            dtypes={"benefit_paid": float, "month": int},
        )
        payouts_df = month_df.pivot_table(
            values="benefit_paid",
            index=month_df.index,
            columns="month",
            aggfunc=one,
        )
        dfs.append(payouts_df)

    if not dfs[0].empty:
        dfs[0].columns = ["benefit_paid_month_0"]
    if not dfs[1].empty:
        dfs[1].columns = [f"benefit_paid_month_{m}" for m in dfs[1].columns]

    return pd.concat(dfs, axis=1).reindex(
        columns=["benefit_paid_month_0"]
        + [f"benefit_paid_month_{m}" for m in range(1, month)]
    )


def get_people_who_might_earn_too_much_or_little(
    year: int, cpr_numbers: list
) -> pd.DataFrame:
    """
    Return people who are on the edge of earning too much or too little

    Parameters
    --------------
    year : int
        Year to return people for
    cpr_numbers : list
        CPR numbers of people to return

    Returns
    -----------
    Dataframe indexed by cpr-number with the following columns:
        - earns_too_little: True if the person earns too little. False otherwise
        - earns_too_much: True if the person earns too much. False otherwise


    Notes
    ------------
    - A person earns too much if he earns so much that he is not eligible for payout
    - A person earns too little if he earns so little that he is not eligible for payout
    """

    # Use the calculation method that is the closest to the given year.
    # For example: If year=2020 and the only calculations methods in the system are from
    # 2022, 2023 and 2024 we use the one from 2022.
    year_dict = {y.year: y for y in Year.objects.all()}
    year_key = min(year_dict.keys(), key=lambda x: abs(x - year))
    calculation_method = year_dict[year_key].calculation_method
    calculate_benefit_func = calculation_method.calculate_float  # type: ignore

    income = get_income_as_dataframe(year, cpr_numbers=cpr_numbers)
    a_income = income[IncomeType.A]
    b_income = income[IncomeType.B]
    df_income = a_income.add(b_income, fill_value=0)

    df = pd.DataFrame()

    df["std_val"] = df_income.std(axis=1).fillna(0)
    df["annual_income"] = df_income.sum(axis=1)
    df["upper"] = df.annual_income + df.std_val
    df["lower"] = df.annual_income - df.std_val

    df["earns_too_little"] = (df.lower.map(calculate_benefit_func) == 0) & (
        df.annual_income.map(calculate_benefit_func) != 0
    )
    df["earns_too_much"] = (df.upper.map(calculate_benefit_func) == 0) & (
        df.annual_income.map(calculate_benefit_func) != 0
    )
    return df


def get_people_in_quarantine(year: int, cpr_numbers: list) -> pd.DataFrame:
    """
    Return people who are in quarantine

    Parameters
    ------------
    year : int
        Year to return people who are inquarantine for
    cpr_numbers : list
        CPR numbers to get quarantine status for

    Returns
    ----------
    df : DataFrame
        Dataframe Indexed by CPR number with two relevant columns:
            - "in_quarantine" which is True/False.
            - "quarantine_reason" which is a string

    Notes
    -------
    People who are in quarantine get all their money paid out in December. They
    get nothing in Jan-Nov.
    """
    quarantine_limit = settings.CALCULATION_QUARANTINE_LIMIT  # type: ignore
    qs = PersonMonth.objects.filter(
        month=12,
        person_year__year__year=year - 1,
        person_year__person__cpr__in=cpr_numbers,
    )
    df = to_dataframe(
        qs,
        index="person_year__person__cpr",
        dtypes={
            "actual_year_benefit": float,
            "prior_benefit_paid": float,
            "benefit_paid": float,
        },
    )
    df_2 = get_people_who_might_earn_too_much_or_little(year - 1, cpr_numbers)

    df["total_benefit_paid"] = df.prior_benefit_paid + df.benefit_paid
    df["error"] = df.total_benefit_paid - df.actual_year_benefit
    df["wrong_payout"] = df.error.fillna(0) > quarantine_limit
    df["earns_too_little"] = df_2.earns_too_little.reindex(df.index, fill_value=False)
    df["earns_too_much"] = df_2.earns_too_much.reindex(df.index, fill_value=False)

    df["in_quarantine"] = df.wrong_payout | df.earns_too_little | df.earns_too_much

    df["quarantine_reason"] = "-"
    df.loc[df.wrong_payout, "quarantine_reason"] = str(
        _("Modtog for meget tilskud i {year}").format(year=year - 1)
    )

    df.loc[df.earns_too_little, "quarantine_reason"] = str(
        _("Tjente for tæt på bundgrænsen i {year}").format(year=year - 1)
    )
    df.loc[df.earns_too_much, "quarantine_reason"] = str(
        _("Tjente for tæt på øverste grænse i {year}").format(year=year - 1)
    )
    df = df.reindex(cpr_numbers)
    df["quarantine_reason"] = df.quarantine_reason.fillna("-")
    df["in_quarantine"] = df.in_quarantine.fillna(False)

    return df


def calculate_benefit(
    month: int,
    year: int,
    cpr: str | None = None,
    engine_a: str | None = None,
    engine_b: str | None = None,
) -> pd.DataFrame:
    """
    Calculate benefit for a specific month

    Parameters
    ---------------
    month: int
        Month to calculate benefit for
    year: int
        Year to calculate benefit for

    Other parameters
    ------------------
    cpr: str
        Person to calculate benefit for

    Returns
    -----------
    df : DataFrame
        Dataframe indexed by cpr-number. Contains the following relevant columns:
            * benefit_paid
            * prior_benefit_paid
            * estimated_year_benefit
            * actual_year_benefit
        The abovementioned columns map one-to-one to a PersonMonth object.
    """
    trivial_limit = settings.CALCULATION_TRIVIAL_LIMIT  # type: ignore
    treshold = float(settings.CALCULATION_STICKY_THRESHOLD)  # type: ignore
    enforce_quarantine = settings.ENFORCE_QUARANTINE  # type: ignore
    if month == 12:
        safety_factor = 1
    else:
        safety_factor = float(settings.CALCULATION_SAFETY_FACTOR)  # type: ignore
    calculation_method = Year.objects.get(year=year).calculation_method
    calculate_benefit_func = calculation_method.calculate_float  # type: ignore
    benefit_cols_this_year = [f"benefit_paid_month_{m}" for m in range(1, month)]

    # Get income estimates for THIS month
    estimates_df = get_income_estimates_df(
        month, year, cpr, engine_a=engine_a, engine_b=engine_b
    )

    # Get payouts for PREVIOUS months (PersonMonth)
    payouts_df = get_payout_df(month, year, cpr=cpr)

    # Combine for ease-of-use
    df = pd.concat([estimates_df, payouts_df], axis=1)

    # Calculate benefit
    df["estimated_year_benefit"] = (
        df.estimated_year_result.fillna(0).map(calculate_benefit_func) * safety_factor
    )
    df["actual_year_benefit"] = df.actual_year_result.fillna(0).map(
        calculate_benefit_func
    )
    df["prior_benefit_paid"] = df.loc[:, benefit_cols_this_year].sum(axis=1)
    df["benefit_this_month"] = (
        (df.estimated_year_benefit - df.prior_benefit_paid) / (13 - month)
    ).round(2)

    # Do not payout if the amount is below zero
    df.loc[df.benefit_this_month < 0, "benefit_this_month"] = 0

    if month < 12:
        # Do not payout if the amount is below the trivial limit
        df.loc[df.benefit_this_month < trivial_limit, "benefit_this_month"] = 0

        # if the amount is very similar to last months amount, use the same amount
        # as last month
        df["benefit_last_month"] = df.loc[:, f"benefit_paid_month_{month-1}"]

        diff = pd.Series(index=df.index)
        I_diff = df.benefit_last_month > 0
        diff_abs = (df.benefit_this_month - df.benefit_last_month).abs()
        diff[I_diff] = diff_abs[I_diff] / df.benefit_last_month[I_diff]
        small_diffs = diff < treshold

        df.loc[small_diffs, "benefit_this_month"] = df.loc[
            small_diffs, "benefit_last_month"
        ]

        # If you are in quarantaine you get nothing (unless it's December)
        if enforce_quarantine:
            df_quarantine = get_people_in_quarantine(year, df.index.to_list())
            df.loc[df_quarantine.in_quarantine, "benefit_this_month"] = 0

    df["benefit_paid"] = df.benefit_this_month
    return df


def calculate_payout_error_for_all_engine_combinations(year):
    """
    Calculates payout error for all engine combinations

    Parameters
    ---------------
    year: int
        Year to calculate payout errors for

    Returns
    ------------
    df: DataFrame
        Dataframe with payout errors.
        Indexed by cpr number. Every column is an (engine_a, engine_b) tuple.
    """

    engines = {
        engine_class
        for engine_class in EstimationEngine.classes()
        if engine_class != SameAsLastMonthEngine
    }

    a_engines = [
        engine for engine in engines if IncomeType.A in engine.valid_income_types
    ]
    b_engines = [
        engine for engine in engines if IncomeType.B in engine.valid_income_types
    ]

    df_error = pd.DataFrame()
    for engine_a in a_engines:
        for engine_b in b_engines:
            df = pd.DataFrame()
            for month in range(1, 13):
                df_payout = calculate_benefit(
                    month,
                    year,
                    engine_a=engine_a.__name__,
                    engine_b=engine_b.__name__,
                )

                df[f"estimated_year_benefit_m{month}"] = (
                    df_payout.estimated_year_benefit
                )

            error = (df.mean(axis=1) - df_payout.actual_year_benefit).abs()
            df_error[(engine_a.__name__, engine_b.__name__)] = error
    return df_error


def get_best_engine(year):
    """
    Get the best A and B estimation engines for a particular year

    Parameters
    --------------
    year : int
        Year to get the best engine for

    Returns
    -----------
    df: DataFrame
        Dataframe indexed by cpr. One column for each income type. Each cell contains
        the engine that is best for that person and income type.

    Notes
    -------
    The algorithm uses last year to find the best engine for the given year
    """

    default_engine_a = PersonYear._meta.get_field(
        "preferred_estimation_engine_a"
    ).get_default()
    default_engine_b = PersonYear._meta.get_field(
        "preferred_estimation_engine_b"
    ).get_default()

    df_error = calculate_payout_error_for_all_engine_combinations(year - 1)

    best_engine = pd.Series(
        [(default_engine_a, default_engine_b)] * len(df_error),
        index=df_error.index,
    )

    min_error = df_error.min(axis=1)

    df_min_error = pd.DataFrame(columns=df_error.columns)
    for col in df_min_error.columns:
        df_min_error[col] = min_error

    df_duplicates = (df_error == df_min_error).sum(axis=1)

    valid_errors = ~min_error.isnull() & (df_duplicates == 1)
    best_engine[valid_errors] = df_error.loc[valid_errors, :].idxmin(axis=1)

    df = pd.DataFrame(index=best_engine.index)
    df["A"] = best_engine.map(lambda t: t[0])
    df["B"] = best_engine.map(lambda t: t[1])

    return df


def isnan(input: np.float64) -> bool:
    return np.isnan(input)


camelcase_re = re.compile(r"((?<=[a-z0-9])[A-Z]|(?!^)[A-Z](?=[a-z]))")


S = TypeVar("S", str, dict)


def camelcase_to_snakecase(input: S) -> S:
    if isinstance(input, dict):
        return {camelcase_to_snakecase(key): value for key, value in input.items()}
    else:
        return camelcase_re.sub("_\\1", input).lower()
