# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
"""This file anonymizes CPR and CVR fields of CSV files.

The functions should work with all CSV-exported spreadsheets."""

import csv


def dictify_csv_file(file_name):
    """Convert CSV file with a header row to a list of dicts."""
    with open(file_name, "r") as f:
        rows = [r for r in csv.reader(f)]
    csv_rows = [{a: b for a, b in zip(rows[0], r)} for r in rows[1:]]

    return csv_rows


def anonymize_csv_field(field_name, files):
    """Overwrite value of a given field in a list of CSV files with a counter.

    Please note: The field *must* be present in all input files, and the files
    in the list of file names *must* exist in the file system.
    """

    csv_data = {file_name: dictify_csv_file(file_name) for file_name in files}

    value_set = set.union(
        *[{e[field_name] for e in csv_data[file_name]} for file_name in csv_data.keys()]
    )

    value_map = {value: num for num, value in enumerate(value_set)}

    print("{} forskellige værdier af feltet {}".format(len(value_set), field_name))

    for file_name in csv_data:
        rows = csv_data[file_name]
        # No point in doing this if there's no data.
        assert len(rows) > 0

        for row in rows:
            row[field_name] = value_map[row[field_name]]
        # print("Ready to write!")
        # break

        with open(file_name, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            headers = list(rows[0].keys())
            writer.writerow(headers)
            for row in rows:
                writer.writerow(list(row.values()))


if __name__ == "__main__":
    cpr_file_names = [
        "a_og_b_2020.csv",
        "a_og_b_2021.csv",
        "a_og_b_2022.csv",
        "a_og_b_2023.csv",
        "forskud_2020.csv",
        "forskud_2021.csv",
        "forskud_2022.csv",
        "forskud_2023.csv",
        "ligning_2020.csv",
        "ligning_2021.csv",
        "ligning_2022.csv",
        "ligning_2023.csv",
    ]
    cvr_file_names = [
        "a_og_b_2020.csv",
        "a_og_b_2021.csv",
        "a_og_b_2022.csv",
        "a_og_b_2023.csv",
    ]

    print(f"Anonymizing field 'CPR'!")
    anonymize_csv_field("CPR", cpr_file_names)

    print(f"Anonymizing field 'CVR'!")
    anonymize_csv_field("Arbejdsgiver CVR", cvr_file_names)
