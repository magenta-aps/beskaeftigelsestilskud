# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
import dataclasses
import re
from decimal import Decimal
from typing import Any, Collection, Dict, Iterable, TypeVar
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Model, QuerySet
from django.utils.translation import gettext_lazy as _
from pandas import DataFrame

from suila.models import (
    IncomeEstimate,
    IncomeType,
    MonthlyIncomeReport,
    PersonMonth,
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


def get_income_as_dataframe(
    year: int, cpr_numbers: Iterable[str] | None = None
) -> dict:
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
    income_qs = MonthlyIncomeReport.objects.filter(year=year)
    if cpr_numbers:
        income_qs = income_qs.filter(
            person_month__person_year__person__cpr__in=cpr_numbers
        )

    output_dict = {}
    for income_type, amount_field in zip(IncomeType, ["a_income", "b_income"]):
        df = to_dataframe(
            qs=income_qs,
            index="person_month__person_year__person__cpr",
            dtypes={amount_field: float, "month": int},
        )
        output_dict[income_type] = df.pivot_table(
            values=amount_field,
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

    estimates_qs = estimates_qs.order_by(
        "person_month__person_year__year__year",
        "person_month__month",
        "person_month__person_year__person__cpr",
    )
    df = to_dataframe(
        estimates_qs,
        index="person_month__person_year__person__cpr",
        dtypes={
            "engine": str,
            "person_month__person_year__preferred_estimation_engine_a": str,
            "person_month__person_year__preferred_estimation_engine_b": str,
            "person_month__person_year__preferred_estimation_engine_u": str,
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

    estimates_dfs: Dict[IncomeType, DataFrame] = {}
    for income_type in IncomeType:
        estimates_dfs[income_type] = df.loc[
            (df.engine == engine_dict[income_type]) & (df.income_type == income_type),
            ["estimated_year_result", "actual_year_result"],
        ]

    # This is where we add together the estimates
    # for A and B income before the benefit is calculated
    return estimates_dfs[IncomeType.A].add(estimates_dfs[IncomeType.B], fill_value=0)


def get_people_who_might_earn_too_much_or_little(
    year: int, cpr_numbers: Iterable[str]
) -> pd.DataFrame:
    """
    Return people who are on the edge of earning too much or too little

    Parameters
    --------------
    year : int
        Year to return people for
    cpr_numbers : Iterable[str]
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


def get_people_in_quarantine(year: int, cpr_numbers: Iterable[str]) -> pd.DataFrame:
    """
    Return people who are in quarantine

    Parameters
    ------------
    year : int
        Year to return people who are inquarantine for
    cpr_numbers : Iterable[str]
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

    quarantine_if_wrong_payout = settings.QUARANTINE_IF_WRONG_PAYOUT  # type: ignore
    quarantine_if_too_much = settings.QUARANTINE_IF_EARNS_TOO_MUCH  # type: ignore
    quarantine_if_too_little = settings.QUARANTINE_IF_EARNS_TOO_LITTLE  # type: ignore

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

    df["in_quarantine"] = False
    df["quarantine_reason"] = "-"

    if quarantine_if_wrong_payout:
        df.in_quarantine = df.in_quarantine | df.wrong_payout
        df.loc[df.wrong_payout, "quarantine_reason"] = str(
            _("Modtog for meget tilskud i {year}").format(year=year - 1)
        )

    if quarantine_if_too_much:
        df.in_quarantine = df.in_quarantine | df.earns_too_much
        df.loc[df.earns_too_much, "quarantine_reason"] = str(
            _("Tjente for tæt på øverste grænse i {year}").format(year=year - 1)
        )

    if quarantine_if_too_little:
        df.in_quarantine = df.in_quarantine | df.earns_too_little
        df.loc[df.earns_too_little, "quarantine_reason"] = str(
            _("Tjente for tæt på bundgrænsen i {year}").format(year=year - 1)
        )

    df = df.reindex(cpr_numbers)
    df["quarantine_reason"] = df.quarantine_reason.fillna("-")
    df["in_quarantine"] = df.in_quarantine.fillna(False)
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


def omit(items: Dict[str, Any], *keys: Collection[str]) -> Dict[str, Any]:
    k = set(keys)
    return {key: value for key, value in items.items() if key not in k}


# isinstance(), except we can avoid circular imports
def is_instance(obj, classname: str) -> bool:
    for cls in obj.__class__.__mro__:
        if cls.__name__ == classname:
            return True
    return False


class SuilaJSONEncoder(DjangoJSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return dataclasses.asdict(obj)
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Model):
            exclude_keys = {"load_id", "exclude_serialization"}
            if hasattr(obj, "exclude_serialization"):
                exclude_keys.update(getattr(obj, "exclude_serialization"))
            return {
                k: v
                for k, v in obj.__dict__.items()
                if not k.startswith("_") and k not in exclude_keys
            }
        if is_instance(obj, "EstimationEngine"):
            return {
                "class": obj.__class__.__name__,
                "description": obj.description,
            }

        return super().default(obj)
