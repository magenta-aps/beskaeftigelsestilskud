# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0
#
# To use keras/tensorflow:
# Install ROCm: https://rocm.docs.amd.com/projects/install-on-linux/en
# /latest/install/quick-start.html
# Install keras: pip install keras
# Install tensorflow: pip install tensorflow

import os
import pickle as pk

import functions
import keras
import matplotlib.pyplot as plt
import pandas as pd
from keras import Input, layers, models
from keras.models import Model
from keras.src import ops
from keras.src.losses.loss import squeeze_or_expand_to_same_rank

pd.set_option("display.large_repr", "info")
pd.set_option("display.max_info_columns", 500)
plt.close("all")

functions.pltdefaults()

output_folder = os.environ["HOME"] + "/Pictures/plots/61666_deep_learning_v4"
functions.makedir(output_folder)

# Load data
df_a, df_b = functions.load_data()
df_a = df_a.fillna(0)
df_b = df_b.fillna(0)
df_combined = df_a + df_b

df_median_a = df_a.T.rolling(12).median().T
df_mean_a = df_a.T.rolling(12).mean().T
df_min_a = df_a.T.rolling(12).min().T
df_max_a = df_a.T.rolling(12).max().T

df_median_b = df_b.T.rolling(12).median().T
df_mean_b = df_b.T.rolling(12).mean().T
df_min_b = df_b.T.rolling(12).min().T
df_max_b = df_b.T.rolling(12).max().T

df_annual_a = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df_a.columns if year in c]
    df_annual_a[year] = df_a.loc[:, cols].sum(axis=1)

df_annual_b = pd.DataFrame()
for year in ["2020", "2021", "2022", "2023"]:
    cols = [c for c in df_a.columns if year in c]
    df_annual_b[year] = df_b.loc[:, cols].sum(axis=1)

month_dict = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "Maj": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Okt": 10,
    "Nov": 11,
    "Dec": 12,
}

# Make training dataset
df = pd.DataFrame()
for col in df_a.columns[12:]:
    print(col)
    year = col.split("(")[1][:-1]

    df_sub = pd.DataFrame()

    # Data
    df_sub["median_salary_a"] = df_median_a[col].values
    df_sub["mean_salary_a"] = df_mean_a[col].values
    df_sub["min_salary_a"] = df_min_a[col].values
    df_sub["max_salary_a"] = df_max_a[col].values
    df_sub["salary_a"] = df_a[col].values
    df_sub["month_number_a"] = month_dict[col.split(" ")[0]]

    df_sub["median_salary_b"] = df_median_b[col].values
    df_sub["mean_salary_b"] = df_mean_b[col].values
    df_sub["min_salary_b"] = df_min_b[col].values
    df_sub["max_salary_b"] = df_max_b[col].values
    df_sub["salary_b"] = df_b[col].values
    df_sub["month_number_b"] = month_dict[col.split(" ")[0]]

    # Target
    df_sub["annual_salary_a"] = df_annual_a[year].values
    df_sub["annual_salary_b"] = df_annual_b[year].values

    df = pd.concat([df, df_sub], axis=0)

# Clean
df = df[df.annual_salary_a < 1_000_000_000]
df = df[df.annual_salary_b < 1_000_000_000]

# Shuffle
df = df.sample(frac=1)
df.index = range(len(df))

# Split in train data, train targets, test data, test targets
test_fraction = 0.8
test_n = int(len(df) * test_fraction)

# %% Custom loss function


def calculate_benefit(
    amount,
    benefit_rate_percent=17.5,
    personal_allowance=58000.0,
    standard_allowance=10000.0,
    max_benefit=15750.0,
    scaledown_rate_percent=6.3,
    scaledown_ceiling=250000.0,
):
    """
    Adapted from functions.calculate_benefit
    """
    zero = 0.0
    benefit_rate = benefit_rate_percent * 0.01
    scaledown_rate = scaledown_rate_percent * 0.01
    rateable_amount = ops.maximum(
        amount - personal_allowance - standard_allowance, zero
    )
    scaledown_amount = ops.maximum(amount - scaledown_ceiling, zero)
    return ops.maximum(
        ops.minimum(benefit_rate * rateable_amount, max_benefit)
        - scaledown_rate * scaledown_amount,
        zero,
    )


def mean_squared_error_on_payout(y_true, y_pred):
    """
    Adapted from keras.losses.MeanSquaredError(y_true, y_pred)
    """

    keras.losses
    y_pred = ops.convert_to_tensor(y_pred)
    y_true = ops.convert_to_tensor(y_true, dtype=y_pred.dtype)
    y_true = calculate_benefit(y_true)
    y_pred = calculate_benefit(y_pred)
    y_true, y_pred = squeeze_or_expand_to_same_rank(y_true, y_pred)

    return ops.mean(ops.abs(y_true - y_pred), axis=-1)


# %%

for income_type in ["a", "b"]:

    cols = [c for c in df.columns if c.endswith(f"_{income_type}")]
    data = df.loc[:, cols[:-1]].to_numpy()
    targets = df.loc[:, cols[-1]].to_numpy()

    train_data = data[range(test_n), :]
    train_targets = targets[range(test_n)]

    test_data = data[range(test_n, len(df)), :]
    test_targets = targets[range(test_n, len(df))]

    # %% Visualize data
    fig, axes = plt.subplots(4, 4, sharex=True, sharey="row", figsize=(22, 13))
    axes = iter(axes.flatten())

    for col in df.columns:
        ax = next(axes)
        ax.plot(df.loc[:200, col])
        ax.set_title(col)

    plt.savefig(output_folder + "/data")

    # %% Set up and train model
    history_filename = f"annual_salary_history_{income_type}.p"
    model_filename = f"annual_salary_model_{income_type}.keras"
    if history_filename in os.listdir(output_folder):

        # Load model
        model = models.load_model(os.path.join(output_folder, model_filename))

        # Load history
        history = pk.load(open(os.path.join(output_folder, history_filename), "rb"))
    else:

        data_input = Input(shape=(train_data.shape[1],), dtype="float32")

        x = layers.Dense(16, activation="relu")(data_input)
        x = layers.Dense(16, activation="relu")(x)
        output = layers.Dense(1, activation="relu")(x)

        model = Model(data_input, output)

        model.summary()

        model.compile(optimizer="rmsprop", loss="mse", metrics=["mae"])

        callbacks = [
            keras.callbacks.TensorBoard(
                log_dir=output_folder, histogram_freq=1, embeddings_freq=1
            )
        ]

        history = model.fit(
            train_data,
            train_targets,
            epochs=15,
            validation_split=0.2,
            batch_size=128,
            callbacks=callbacks,
        )

        pk.dump(history, open(os.path.join(output_folder, history_filename), "wb"))
        model.save(os.path.join(output_folder, model_filename))

    # %% Plot results
    functions.plot_results(history)

    current_fig = plt.gcf().number
    plt.figure(current_fig)
    plt.savefig(os.path.join(output_folder, f"model_history_{income_type}.png"))

    plt.figure(current_fig - 1)
    plt.savefig(os.path.join(output_folder, f"model_history_loss_{income_type}.png"))

    # %% Calculate modelled annual salary
    modelled_data = model(test_data).numpy()[:, 0]

    # Plot modelled annual salary and actual annual salary
    plt.figure()
    plt.plot(modelled_data[:200])
    plt.plot(test_targets[:200])
    plt.savefig(os.path.join(output_folder, f"modelled_salary_ts_{income_type}.png"))

    error = test_targets - modelled_data
    plt.figure()
    plt.hist(error[(error < 500_000) & (error > -500_000)], bins=100)
    plt.savefig(os.path.join(output_folder, f"modelled_salary_error_{income_type}.png"))
