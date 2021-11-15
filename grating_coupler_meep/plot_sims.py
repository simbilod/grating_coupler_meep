import pathlib
import pandas as pd
from omegaconf import OmegaConf
import matplotlib.pyplot as plt
import numpy as np


def plot_fiber_xposition_max_power():
    dirpath = pathlib.Path(__file__).parent / "data"

    fiber_xpositions = []
    s21_max = []

    for filepath_csv in dirpath.glob("*.csv"):
        filepath_yaml = filepath_csv.with_suffix(".yml")
        settings = OmegaConf.load(filepath_yaml)
        df = pd.read_csv(filepath_csv)
        s21 = 10 * np.log10(df.s21m)

        fiber_xposition = settings.settings.fiber_xposition
        fiber_xpositions.append(fiber_xposition)
        s21_max.append(max(s21))

    plt.plot(fiber_xpositions, s21_max, ".")
    plt.xlabel("fiber_xposition")
    plt.ylabel("max S21 (dB)")
    plt.show()


def plot_fiber_xposition_spectrum(
    wavelength_min: float = 1.5,
    wavelength_max: float = 1.6,
    wavelength_points: int = 50,
):
    dirpath = pathlib.Path(__file__).parent / "data"

    fiber_xpositions = []
    s21_max = []
    wavelengths = np.linspace(wavelength_min, wavelength_max, wavelength_points)

    for filepath_csv in dirpath.glob("*.csv"):
        filepath_yaml = filepath_csv.with_suffix(".yml")
        settings = OmegaConf.load(filepath_yaml)
        df = pd.read_csv(filepath_csv)
        s21 = 10 * np.log10(df.s21m)

        fiber_xposition = settings.settings.fiber_xposition
        fiber_xpositions.append(fiber_xposition)
        s21_max.append(max(s21))
        plt.plot(wavelengths, s21, label=str(fiber_xposition))

    plt.xlabel("wavelength")
    plt.ylabel("S21 (dB)")
    plt.legend()
    plt.show()


if __name__ == "__main__":
    plot_fiber_xposition_spectrum()
