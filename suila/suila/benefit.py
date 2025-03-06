# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date
from fractions import Fraction

import numpy as np
import pandas as pd
from common import utils
from common.utils import to_dataframe
from django.conf import settings
from more_itertools import one
from numpy import float64

# from suila.estimation import EstimationEngine, MonthlyContinuationEngine
from suila.models import PersonMonth, PersonYearAssessment, Year


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
    threshold = float(settings.CALCULATION_STICKY_THRESHOLD)  # type: ignore
    enforce_quarantine = settings.ENFORCE_QUARANTINE  # type: ignore
    quarantine_weight = Fraction(
        # Using fraction because we don't like float-point errors
        settings.QUARANTINE_WEIGHTS[month - 1],  # type: ignore
        12,
    )
    accumulated_weight = Fraction(
        sum(settings.QUARANTINE_WEIGHTS[0 : month - 1]), 12  # type: ignore
    )
    if month == 12:
        safety_factor = 1
    else:
        safety_factor = float(settings.CALCULATION_SAFETY_FACTOR)  # type: ignore
    calculation_method = Year.objects.get(year=year).calculation_method
    calculate_benefit_func = calculation_method.calculate_float  # type: ignore
    benefit_cols_this_year = [f"benefit_paid_month_{m}" for m in range(1, month)]

    month_qs = PersonMonth.objects.filter(person_year__year_id=year, month=month)
    if cpr:
        month_qs = month_qs.filter(person_year__person__cpr=cpr)
    month_qs = PersonMonth.signal_qs(month_qs)
    month_df = to_dataframe(
        month_qs,
        index="person_year__person__cpr",
        dtypes={
            "signal": bool,
        },
    )

    # Get income estimates for THIS month
    estimates_df = utils.get_income_estimates_df(month, year, cpr, engine_a=engine_a)

    # Læg B-indkomst fra forskudsopgørelse til
    assessment_qs = PersonYearAssessment.objects.filter(
        person_year__year_id=year, latest=True
    )
    if cpr:
        assessment_qs = assessment_qs.filter(person_year__person__cpr=cpr)
    assessment_qs = PersonYearAssessment.annotate_assessed_b_income(assessment_qs)
    b_income_df = to_dataframe(
        assessment_qs,
        index="person_year__person__cpr",
        dtypes={
            "assessed_b_income_sum": float,
        },
    )

    # Get payouts for PREVIOUS months (PersonMonth)
    payouts_df = get_payout_df(month, year, cpr=cpr)

    # Combine for ease-of-use
    df = pd.concat([month_df, estimates_df, payouts_df, b_income_df], axis=1)

    # Any months not found in concatenation have been set to NaN, replace with False
    df["signal"] = df["signal"].fillna(False)

    df["calculation_basis"] = df["estimated_year_result"].add(
        df["assessed_b_income_sum"], fill_value=0
    )

    # Only payout if we have a signal
    df.loc[np.logical_not(df["signal"]), "calculation_basis"] = 0

    # Calculate benefit
    df["estimated_year_benefit"] = (
        df.calculation_basis.fillna(0).map(calculate_benefit_func) * safety_factor
    )
    df["actual_year_benefit"] = (
        df.actual_year_result.add(df["assessed_b_income_sum"], fill_value=0)
        .fillna(0)
        .map(calculate_benefit_func)
    )
    df["prior_benefit_paid"] = df.loc[:, benefit_cols_this_year].sum(axis=1)
    df["remaining_benefit_for_year"] = df.estimated_year_benefit - df.prior_benefit_paid
    df["benefit_this_month"] = (df.remaining_benefit_for_year / (13 - month)).round(2)

    # Do not payout if the amount is below zero
    df.loc[df.benefit_this_month < 0, "benefit_this_month"] = 0

    if month != 12:
        # Do not payout if the amount is below the trivial limit
        df.loc[df.benefit_this_month < trivial_limit, "benefit_this_month"] = 0

    if threshold > 0 and month not in (1, 12):  # type: ignore
        # if the amount is very similar to last month's amount, use the same amount
        # as last month
        df["benefit_last_month"] = df.loc[:, f"benefit_paid_month_{month-1}"]
        diff = pd.Series(index=df.index)
        I_diff = df.benefit_last_month > 0
        diff_abs = (df.benefit_this_month - df.benefit_last_month).abs()
        diff[I_diff] = diff_abs[I_diff] / df.benefit_last_month[I_diff]
        small_diffs = diff < threshold
        df.loc[small_diffs, "benefit_this_month"] = df.loc[
            small_diffs, "benefit_last_month"
        ]

    # If you are in quarantine you get nothing (unless it's for october)
    if enforce_quarantine:
        df_quarantine = utils.get_people_in_quarantine(year, df.index.to_list())
        if quarantine_weight <= 0:
            weight_on_remainder: Fraction = Fraction(0, 1)
        else:
            # quarantine_weight = factor for year payment to month payment
            # we need a factor for `remaining year payment` to month payment
            # that is, which portion of the remainder should be paid out this month:
            #
            # accumulated_weight is how big a proportion
            # of year payment we already have paid out (e.g. 10/12)
            #
            # 1 - accumulated_weight is how big
            # a proportion we have yet to pay out this year (e.g. 2/12)
            #
            # quarantine_weight / (1 - accumulated_weight)
            # is how much of that proportion is to be paid out this month
            # (e.g. half of the proportion, thus we pay out half of the remainder)
            weight_on_remainder = quarantine_weight / (1 - accumulated_weight)
        df.loc[df_quarantine.in_quarantine, "benefit_this_month"] = (
            df.remaining_benefit_for_year * float64(weight_on_remainder)
        )
        df.loc[
            df_quarantine.in_quarantine, "remaining_benefit_for_year"
        ] -= df.benefit_this_month

    df["benefit_paid"] = np.ceil(df["benefit_this_month"])

    return df


#
# def calculate_payout_error_for_all_engine_combinations(year, cpr: str | None = None):
#     """
#     Calculates payout error for all engine combinations
#
#     Parameters
#     ---------------
#     year: int
#         Year to calculate payout errors for
#
#     Returns
#     ------------
#     df: DataFrame
#         Dataframe with payout errors.
#         Indexed by cpr number. Every column is an (engine_a, engine_b) tuple.
#     """
#
#     engines = {
#         engine_class
#         for engine_class in EstimationEngine.classes()
#         if engine_class != MonthlyContinuationEngine
#     }
#
#     a_engines = [
#         engine for engine in engines if IncomeType.A in engine.valid_income_types
#     ]
#     b_engines = [
#         engine for engine in engines if IncomeType.B in engine.valid_income_types
#     ]
#
#     df_error = pd.DataFrame()
#     for engine_a in a_engines:
#         for engine_b in b_engines:
#             df = pd.DataFrame()
#             for month in range(1, 13):
#                 df_payout = calculate_benefit(
#                     month,
#                     year,
#                     cpr,
#                     engine_a=engine_a.__name__,
#                     engine_b=engine_b.__name__,
#                 )
#
#                 df[f"estimated_year_benefit_m{month}"] = (
#                     df_payout.estimated_year_benefit
#                 )
#
#             error = (df.mean(axis=1) - df_payout.actual_year_benefit).abs()
#             df_error[(engine_a.__name__, engine_b.__name__)] = error
#     return df_error
#
#
def get_best_engine(year, cpr: str | None = None):
    pass  # pragma: no cover


#     """
#     Get the best A and B estimation engines for a particular year
#
#     Parameters
#     --------------
#     year : int
#         Year to get the best engine for
#
#     Returns
#     -----------
#     df: DataFrame
#         Dataframe indexed by cpr. One column for each income type. Each cell contains
#         the engine that is best for that person and income type.
#
#     Notes
#     -------
#     The algorithm uses last year to find the best engine for the given year
#     """
#
#     default_engine_a = PersonYear._meta.get_field(
#         "preferred_estimation_engine_a"
#     ).get_default()
#     default_engine_b = PersonYear._meta.get_field(
#         "preferred_estimation_engine_b"
#     ).get_default()
#
#     df_error = calculate_payout_error_for_all_engine_combinations(year - 1, cpr)
#
#     best_engine = pd.Series(
#         [(default_engine_a, default_engine_b)] * len(df_error),
#         index=df_error.index,
#     )
#
#     min_error = df_error.min(axis=1)
#
#     df_min_error = pd.DataFrame(columns=df_error.columns)
#     for col in df_min_error.columns:
#         df_min_error[col] = min_error
#
#     df_duplicates = (df_error == df_min_error).sum(axis=1)
#
#     valid_errors = ~min_error.isnull() & (df_duplicates == 1)
#     best_engine[valid_errors] = df_error.loc[valid_errors, :].idxmin(axis=1)
#
#     df = pd.DataFrame(index=best_engine.index)
#     df["A"] = best_engine.map(lambda t: t[0])
#     df["B"] = best_engine.map(lambda t: t[1])
#
#     return df


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
        month_df = utils.to_dataframe(
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


def get_payout_date(year: int, month: int) -> date:
    """
    Returns the date of a given month's third tuesday.
    """
    weekday_of_first_day = date(year, month, 1).weekday()
    first_tuesday = 9 - weekday_of_first_day
    if first_tuesday > 7:
        first_tuesday -= 7
    return date(year, month, first_tuesday + 14)
