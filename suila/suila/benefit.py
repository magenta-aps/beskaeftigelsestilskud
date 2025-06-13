# SPDX-FileCopyrightText: 2025 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from datetime import date, timedelta
from fractions import Fraction

import numpy as np
import pandas as pd
from common import utils
from common.utils import to_dataframe
from django.conf import settings
from more_itertools import one
from numpy import float64

from suila.models import PersonMonth, PersonYear, TaxScope, Year


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
            * benefit_calculated
            * prior_benefit_transferred
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
    benefit_cols_this_year = [f"benefit_transferred_month_{m}" for m in range(1, month)]

    month_qs = PersonMonth.objects.filter(
        person_year__year_id=year, month=month
    ).order_by("person_year__person__cpr")
    if cpr:
        month_qs = month_qs.filter(person_year__person__cpr=cpr)
    # Only consider people who are FULDT_SKATTEPLIGTIG
    month_qs.filter(person_year__tax_scope=TaxScope.FULDT_SKATTEPLIGTIG)
    month_qs = PersonMonth.signal_qs(month_qs)
    month_df = to_dataframe(
        month_qs,
        index="person_year__person__cpr",
        dtypes={
            "has_signal": bool,
        },
    )

    # Get income estimates for THIS month
    estimates_df = utils.get_income_estimates_df(month, year, cpr, engine_a=engine_a)

    # Læg B-indkomst fra forskudsopgørelse til
    person_year_qs = PersonYear.objects.filter(year_id=year)
    if cpr:
        person_year_qs = person_year_qs.filter(person__cpr=cpr)

    assessment_df = to_dataframe(
        person_year_qs,
        index="person__cpr",
        dtypes={
            "b_income": float,
            "b_expenses": float,
            "catchsale_expenses": float,
            "person__paused": bool,
            "person__annual_income_estimate": float,
        },
    )

    # Get payouts for PREVIOUS months (PersonMonth)
    payouts_df = get_payout_df(month, year, cpr=cpr)

    # Combine for ease-of-use
    df = pd.concat([month_df, estimates_df, payouts_df, assessment_df], axis=1)

    # Any months not found in concatenation have been set to NaN, replace with False
    df["has_signal"] = df["has_signal"].fillna(False)

    df["calculation_basis"] = (
        df["estimated_year_result"]
        .add(df["b_income"], fill_value=0)
        .sub(df["b_expenses"], fill_value=0)
        .sub(df["catchsale_expenses"], fill_value=0)
    )

    # If annual income is set on a Person object, use that.
    has_income_estimate = df.annual_income_estimate.notna()
    df.loc[has_income_estimate, "calculation_basis"] = df.annual_income_estimate

    # Only payout if we have a signal
    df.loc[np.logical_not(df["has_signal"]), "calculation_basis"] = 0

    # Calculate benefit
    df["estimated_year_benefit"] = (
        df.calculation_basis.fillna(0).map(calculate_benefit_func) * safety_factor
    )
    df["actual_year_benefit"] = (
        df.actual_year_result.add(df["b_income"], fill_value=0)
        .sub(df["b_expenses"], fill_value=0)
        .sub(df["catchsale_expenses"], fill_value=0)
        .fillna(0)
        .map(calculate_benefit_func)
    )
    df["prior_benefit_transferred"] = df.loc[:, benefit_cols_this_year].sum(axis=1)
    df["remaining_benefit_for_year"] = (
        df.estimated_year_benefit - df.prior_benefit_transferred
    )
    df["benefit_this_month"] = (df.remaining_benefit_for_year / (13 - month)).round(2)

    # Do not payout if the amount is below zero
    df.loc[df.benefit_this_month < 0, "benefit_this_month"] = 0

    if month != 12:
        # Do not payout if the amount is below the trivial limit
        df.loc[df.benefit_this_month < trivial_limit, "benefit_this_month"] = 0

    if threshold > 0 and month not in (1, 12):  # type: ignore
        # if the amount is very similar to last month's amount, use the same amount
        # as last month
        df["benefit_last_month"] = df.loc[:, f"benefit_transferred_month_{month-1}"]
        diff = pd.Series(index=df.index)
        I_diff = df.benefit_last_month > 0
        diff_abs = (df.benefit_this_month - df.benefit_last_month).abs()
        diff[I_diff] = diff_abs[I_diff] / df.benefit_last_month[I_diff]
        small_diffs = diff < threshold
        df.loc[small_diffs, "benefit_this_month"] = df.loc[
            small_diffs, "benefit_last_month"
        ]

    # If you are on pause you get nothing (also not in December)
    # Man får pengene på kontoen når årsopgørelsen er færdig (august året efter).
    df.loc[df.paused.fillna(False), "benefit_this_month"] = 0

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

    # Do not payout if the amount is negative
    df.loc[df.benefit_this_month < 0, "benefit_this_month"] = 0

    df["benefit_calculated"] = np.ceil(df["benefit_this_month"])

    return df


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
    The "benefit_transferred_month_0" column corresponds to December of last year.

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
            dtypes={"benefit_transferred": float, "month": int},
        )
        payouts_df = month_df.pivot_table(
            values="benefit_transferred",
            index=month_df.index,
            columns="month",
            aggfunc=one,
        )
        dfs.append(payouts_df)

    if not dfs[0].empty:
        dfs[0].columns = ["benefit_transferred_month_0"]
    if not dfs[1].empty:
        dfs[1].columns = [f"benefit_transferred_month_{m}" for m in dfs[1].columns]

    return pd.concat(dfs, axis=1).reindex(
        columns=["benefit_transferred_month_0"]
        + [f"benefit_transferred_month_{m}" for m in range(1, month)]
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


def get_calculation_date(year: int, month: int) -> date:
    """Get date for when to do calculations in a month

    The day before the 2nd tuesday in a month - Can be changed by modifying
    `settings.CALCULATION_DATE_PAYOUT_DATE_OFFSET_DAYS`.
    """
    return get_payout_date(year, month) - timedelta(
        days=settings.CALCULATION_DATE_PAYOUT_DATE_OFFSET_DAYS  # type: ignore
    )


def get_eboks_date(year: int, month: int):
    """Get date for when to send EBOKS messages to citizens.

    The day before the 3rd tuesday in the month
    """

    return get_payout_date(year, month) - timedelta(
        days=settings.EBOKS_DATE_PAYOUT_DATE_OFFSET_DAYS  # type: ignore
    )
