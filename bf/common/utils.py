# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import numpy as np
import pandas as pd
from django.db.models import QuerySet

from bf.models import IncomeType, MonthlyAIncomeReport, MonthlyBIncomeReport


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
    # Normalize data
    values_norm = values / np.nanmean(values)

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
    return df.astype(dtypes)


def get_income_as_dataframe(year: int) -> pd.DataFrame:
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
