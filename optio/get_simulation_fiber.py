"""SMF specs from photonics.byu.edu/FiberOpticConnectors.parts/images/smf28.pdf

MFD:

- 10.4 for Cband
- 9.2 for Oband

TODO:

- verify with lumerical sims
- enable mpi run from python

"""

import sys
from functools import partial
from typing import Any, Dict, Optional, Tuple

import hashlib
import time
import pathlib
import omegaconf
import pandas as pd
import pydantic

import meep as mp
import numpy as np
import fire

# from gdsfactory.simulation.modes import Mode
from gdsfactory.simulation.modes.types import *

# from optio.visualization import plotStructure_fromSimulation

# sys.path.append("../../../meep_dev/meep/python/")
# from visualization import plot2D

nm = 1e-3
nSi = 3.47
nSiO2 = 1.44

Floats = Tuple[float, ...]


def dict_to_name(**kwargs) -> str:
    """Returns name from a dict."""
    kv = []

    for key in sorted(kwargs):
        if isinstance(key, str):
            value = kwargs[key]
            if value is not None:
                kv += [f"{key}{to_string(value)}"]
    return "_".join(kv)


def to_string(value):
    if isinstance(value, list):
        settings_string_list = [to_string(i) for i in value]
        return "_".join(settings_string_list)
    if isinstance(value, dict):
        return dict_to_name(**value)
    else:
        return str(value)


def fiber_ncore(fiber_numerical_aperture, fiber_nclad):
    return (fiber_numerical_aperture ** 2 + fiber_nclad ** 2) ** 0.5


def get_simulation_fiber(
    # grating parameters
    period: float = 0.66,
    fill_factor: float = 0.5,
    widths: Optional[Floats] = None,
    gaps: Optional[Floats] = None,
    n_periods: int = 30,
    etch_depth: float = 70 * nm,
    # fiber parameters,
    fiber_angle_deg: float = 20.0,
    fiber_xposition: float = 1.0,
    fiber_core_diameter: float = 10.4,
    fiber_numerical_aperture: float = 0.14,
    fiber_nclad: float = nSiO2,
    # material parameters
    ncore: float = nSi,
    ncladtop: float = nSiO2,
    ncladbottom: float = nSiO2,
    nsubstrate: float = nSi,
    # stack parameters
    pml_thickness: float = 1.0,
    substrate_thickness: float = 1.0,
    bottom_clad_thickness: float = 2.0,
    core_thickness: float = 220 * nm,
    top_clad_thickness: float = 2.0,
    air_gap_thickness: float = 1.0,
    fiber_thickness: float = 2.0,
    # simulation parameters
    res: int = 64,  # pixels/um
    wavelength_min: float = 1.4,
    wavelength_max: float = 1.7,
    wavelength_points: int = 150,
    eps_averaging: bool = False,
    fiber_port_y_offset_from_air: float = 1,
    waveguide_port_x_offset_from_grating_start: float = 10,
    fiber_port_x_size: Optional[float] = None,
    # **settings,
) -> Dict[str, Any]:
    """Returns simulation results from grating coupler with fiber.
    na**2 = ncore**2 - nclad**2
    ncore = sqrt(na**2 + ncore**2)

    Args:
        TODO
    """
    wavelengths = np.linspace(wavelength_min, wavelength_max, wavelength_points)
    wavelength = np.mean(wavelengths)
    freqs = 1 / wavelengths
    widths = widths or n_periods * [period * fill_factor]
    gaps = gaps or n_periods * [period * (1 - fill_factor)]

    settings = dict(
        widths=widths,
        gaps=gaps,
        n_periods=n_periods,
        etch_depth=etch_depth,
        fiber_angle_deg=fiber_angle_deg,
        fiber_xposition=fiber_xposition,
        fiber_core_diameter=fiber_core_diameter,
        fiber_numerical_aperture=fiber_numerical_aperture,
        fiber_nclad=fiber_nclad,
        ncore=ncore,
        ncladtop=ncladtop,
        ncladbottom=ncladbottom,
        nsubstrate=nsubstrate,
        pml_thickness=pml_thickness,
        substrate_thickness=substrate_thickness,
        bottom_clad_thickness=bottom_clad_thickness,
        core_thickness=core_thickness,
        top_clad_thickness=top_clad_thickness,
        air_gap_thickness=air_gap_thickness,
        fiber_thickness=fiber_thickness,
        res=res,
        wavelength_min=wavelength_min,
        wavelength_max=wavelength_max,
        wavelength_points=wavelength_points,
        eps_averaging=eps_averaging,
        fiber_port_y_offset_from_air=fiber_port_y_offset_from_air,
        waveguide_port_x_offset_from_grating_start=waveguide_port_x_offset_from_grating_start,
    )
    settings_string = to_string(settings)
    settings_hash = hashlib.md5(settings_string.encode()).hexdigest()[:8]

    # Angle in radians
    fiber_angle = np.radians(fiber_angle_deg)

    # Z (Y)-domain
    sz = (
        +pml_thickness
        + substrate_thickness
        + bottom_clad_thickness
        + core_thickness
        + top_clad_thickness
        + air_gap_thickness
        + fiber_thickness
        + pml_thickness
    )
    # XY (X)-domain
    # Assume fiber port dominates
    fiber_port_y = (
        -sz / 2
        + core_thickness
        + top_clad_thickness
        + air_gap_thickness
        + fiber_port_y_offset_from_air
    )
    fiber_port_x_offset_from_angle = np.abs(fiber_port_y * np.tan(fiber_angle))
    sxy = (
        3.5 * fiber_core_diameter
        + 2 * pml_thickness
        + 2 * fiber_port_x_offset_from_angle
    )

    # length_grating = np.sum(widths) + np.sum(gaps)

    # Materials from indices
    core_material = mp.Medium(index=ncore)
    top_clad_material = mp.Medium(index=ncladtop)
    bottom_clad_material = mp.Medium(index=ncladbottom)
    fiber_ncore = (fiber_numerical_aperture ** 2 + fiber_nclad ** 2) ** 0.5
    fiber_clad_material = mp.Medium(index=fiber_nclad)
    fiber_core_material = mp.Medium(index=fiber_ncore)

    # Useful reference point
    grating_start = (
        -fiber_xposition
    )  # Since fiber dominates, keep it centered and offset the grating

    # Initialize domain x-z plane simulation
    cell_size = mp.Vector3(sxy, sz)

    # Ports (position, sizes, directions)
    fiber_port_y = -sz / 2 + (
        +pml_thickness
        + substrate_thickness
        + bottom_clad_thickness
        + core_thickness
        + top_clad_thickness
        + air_gap_thickness
        + fiber_port_y_offset_from_air
    )
    fiber_port_center = mp.Vector3(fiber_port_x_offset_from_angle, fiber_port_y)
    fiber_port_size =  fiber_port_x_size or mp.Vector3(3.5 * fiber_core_diameter, 0, 0)
    fiber_port_direction = mp.Vector3(y=-1).rotate(mp.Vector3(z=1), -1 * fiber_angle)

    waveguide_port_y = -sz / 2 + (
        +pml_thickness
        + substrate_thickness
        + bottom_clad_thickness / 2
        + core_thickness / 2
        + top_clad_thickness / 2
    )
    waveguide_port_x = grating_start - waveguide_port_x_offset_from_grating_start
    waveguide_port_center = mp.Vector3(
        waveguide_port_x, waveguide_port_y
    )  # grating_start - dtaper, 0)
    waveguide_port_size = mp.Vector3(
        0, bottom_clad_thickness + core_thickness / 2 + top_clad_thickness
    )
    waveguide_port_direction = mp.X

    # Geometry
    fiber_clad = 120
    hfiber_geom = 200  # Some large number to make fiber extend into PML

    geometry = []
    # Fiber (defined first to be overridden)
    geometry.append(
        mp.Block(
            material=fiber_clad_material,
            center=mp.Vector3(0, waveguide_port_y - core_thickness / 2),
            size=mp.Vector3(fiber_clad, hfiber_geom),
            e1=mp.Vector3(x=1).rotate(mp.Vector3(z=1), -1 * fiber_angle),
            e2=mp.Vector3(y=1).rotate(mp.Vector3(z=1), -1 * fiber_angle),
        )
    )
    geometry.append(
        mp.Block(
            material=fiber_core_material,
            center=mp.Vector3(x=0),
            size=mp.Vector3(fiber_core_diameter, hfiber_geom),
            e1=mp.Vector3(x=1).rotate(mp.Vector3(z=1), -1 * fiber_angle),
            e2=mp.Vector3(y=1).rotate(mp.Vector3(z=1), -1 * fiber_angle),
        )
    )

    # Air gap
    geometry.append(
        mp.Block(
            material=mp.air,
            center=mp.Vector3(
                0,
                -sz / 2
                + (
                    +pml_thickness
                    + substrate_thickness
                    + bottom_clad_thickness
                    + core_thickness
                    + top_clad_thickness
                    + air_gap_thickness / 2
                ),
            ),
            size=mp.Vector3(mp.inf, air_gap_thickness),
        )
    )
    # Top cladding
    geometry.append(
        mp.Block(
            material=top_clad_material,
            center=mp.Vector3(
                0,
                -sz / 2
                + (
                    +pml_thickness
                    + substrate_thickness
                    + bottom_clad_thickness
                    + core_thickness / 2
                    + top_clad_thickness / 2
                ),
            ),
            size=mp.Vector3(mp.inf, core_thickness + top_clad_thickness),
        )
    )
    # Bottom cladding
    geometry.append(
        mp.Block(
            material=bottom_clad_material,
            center=mp.Vector3(
                0,
                -sz / 2
                + (+pml_thickness + substrate_thickness + bottom_clad_thickness / 2),
            ),
            size=mp.Vector3(mp.inf, bottom_clad_thickness),
        )
    )

    # waveguide
    geometry.append(
        mp.Block(
            material=core_material,
            center=mp.Vector3(
                0,
                -sz / 2
                + (
                    +pml_thickness
                    + substrate_thickness
                    + bottom_clad_thickness
                    + core_thickness / 2
                ),
            ),
            size=mp.Vector3(mp.inf, core_thickness),
        )
    )

    # grating etch
    x = grating_start
    for width, gap in zip(widths, gaps):
        geometry.append(
            mp.Block(
                material=top_clad_material,
                center=mp.Vector3(
                    x + gap / 2,
                    -sz / 2
                    + (
                        +pml_thickness
                        + substrate_thickness
                        + bottom_clad_thickness
                        + core_thickness
                        - etch_depth / 2
                    ),
                ),
                size=mp.Vector3(gap, etch_depth),
            )
        )
        x += width + gap

    # Substrate
    geometry.append(
        mp.Block(
            material=mp.Medium(index=nsubstrate),
            center=mp.Vector3(0, -sz / 2 + pml_thickness / 2 + substrate_thickness / 2),
            size=mp.Vector3(mp.inf, pml_thickness + substrate_thickness),
        )
    )

    # PMLs
    boundary_layers = [mp.PML(pml_thickness)]

    # mode frequency
    fcen = 1 / wavelength
    fwidth = 0.2 * fcen  # (wavelength_max - wavelength_min)

    # Waveguide source
    sources_directions = [mp.X]
    sources = [
        mp.EigenModeSource(
            src=mp.GaussianSource(frequency=fcen, fwidth=fwidth),
            size=waveguide_port_size,
            center=waveguide_port_center,
            eig_band=1,
            direction=sources_directions[0],
            eig_match_freq=True,
            eig_parity=mp.ODD_Z,
        )
    ]

    # Ports
    waveguide_monitor_port = mp.ModeRegion(
        center=waveguide_port_center + mp.Vector3(x=0.2), size=waveguide_port_size
    )
    fiber_monitor_port = mp.ModeRegion(
        center=fiber_port_center - mp.Vector3(y=0.2), size=fiber_port_size
    )

    sim = mp.Simulation(
        resolution=res,
        cell_size=cell_size,
        boundary_layers=boundary_layers,
        geometry=geometry,
        sources=sources,
        dimensions=2,
        eps_averaging=eps_averaging,
    )
    waveguide_monitor = sim.add_mode_monitor(
        freqs, waveguide_monitor_port, yee_grid=True
    )
    fiber_monitor = sim.add_mode_monitor(freqs, fiber_monitor_port)
    field_monitor_point = (0, 0, 0)

    return dict(
        sim=sim,
        cell_size=cell_size,
        freqs=freqs,
        fcen=fcen,
        waveguide_monitor=waveguide_monitor,
        waveguide_port_direction=waveguide_port_direction,
        fiber_monitor=fiber_monitor,
        fiber_angle_deg=fiber_angle_deg,
        sources=sources,
        field_monitor_point=field_monitor_point,
        initialized=False,
        settings=settings,
    )


def get_port_1D_eigenmode(
    sim_dict,
    band_num=1,
    fiber_angle_deg=15,
):
    """

    Args:
        sim_dict: simulation dict
        band_num: band number to solve for

    Returns:
        Mode object compatible with /modes plugin
    """
    # Initialize
    sim = sim_dict["sim"]
    source = sim_dict["sources"][0]
    waveguide_monitor = sim_dict["waveguide_monitor"]
    fiber_monitor = sim_dict["fiber_monitor"]

    # Obtain source frequency
    fsrc = source.src.frequency

    # Obtain xsection
    center_fiber = fiber_monitor.regions[0].center
    size_fiber = fiber_monitor.regions[0].size
    center_waveguide = waveguide_monitor.regions[0].center
    size_waveguide = waveguide_monitor.regions[0].size

    # Solve for the modes
    if sim_dict["initialized"] is False:
        sim.init_sim()
        sim_dict["initialized"] = True

    # Waveguide
    eigenmode_waveguide = sim.get_eigenmode(
        direction=mp.X,
        where=mp.Volume(center=center_waveguide, size=size_waveguide),
        band_num=band_num,
        kpoint=mp.Vector3(
            fsrc * 3.48, 0, 0
        ),  # Hardcoded index for now, pull from simulation eventually
        frequency=fsrc,
    )
    ys_waveguide = np.linspace(
        center_waveguide.y - size_waveguide.y / 2,
        center_waveguide.y + size_waveguide.y / 2,
        int(sim.resolution * size_waveguide.y),
    )
    x_waveguide = center_waveguide.x

    # Fiber
    eigenmode_fiber = sim.get_eigenmode(
        direction=mp.NO_DIRECTION,
        where=mp.Volume(center=center_fiber, size=size_fiber),
        band_num=band_num,
        kpoint=mp.Vector3(0, fsrc * 1.45, 0).rotate(
            mp.Vector3(z=1), -1 * np.radians(fiber_angle_deg)
        ),  # Hardcoded index for now, pull from simulation eventually
        frequency=fsrc,
    )
    xs_fiber = np.linspace(
        center_fiber.x - size_fiber.x / 2,
        center_fiber.x + size_fiber.x / 2,
        int(sim.resolution * size_fiber.x),
    )
    y_fiber = center_fiber.y

    return (
        x_waveguide,
        ys_waveguide,
        eigenmode_waveguide,
        xs_fiber,
        y_fiber,
        eigenmode_fiber,
    )


def plot(sim, eps_parameters=None):
    """
    sim: simulation object
    """
    sim.plot2D(eps_parameters=eps_parameters)
    # plt.colorbar()


if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import inspect

    # results = {}
    # for angle in [10]:  # np.linspace(0,360,72):
    #     print(angle)
    #     (
    #         x_waveguide,
    #         ys_waveguide,
    #         eigenmode_waveguide,
    #         xs_fiber,
    #         y_fiber,
    #         eigenmode_fiber,
    #     ) = get_port_1D_eigenmode(sim_dict, band_num=1, fiber_angle_deg=angle)

    #     Ez_fiber = np.zeros(len(xs_fiber), dtype=np.complex128)
    #     for i in range(len(xs_fiber)):
    #         Ez_fiber[i] = eigenmode_fiber.amplitude(
    #             mp.Vector3(xs_fiber[i], y_fiber, 0), mp.Ez
    #         )

    #     plt.plot(xs_fiber, np.abs(Ez_fiber))
    #     plt.show()

    # Ez_waveguide = np.zeros(len(ys_waveguide), dtype=np.complex128)
    # for i in range(len(ys_waveguide)):
    #     Ez_waveguide[i] = eigenmode_waveguide.amplitude(
    #                 mp.Vector3(x_waveguide, ys_waveguide[i], 0), mp.Ez
    #             )

    # plt.plot(ys_waveguide, np.abs(Ez_waveguide))
    # plt.xlabel('y (um)')
    # plt.ylabel('Ez (a.u.)')
    # plt.savefig('waveguide.png')

    # # plt.figure()

    # # Ez_fiber = np.zeros(len(xs_fiber), dtype=np.complex128)
    # # for i in range(len(xs_fiber)):
    # #     Ez_fiber[i] = eigenmode_fiber.amplitude(
    # #                 mp.Vector3(xs_fiber[i], y_fiber, 0), mp.Ez
    # #             )

    # # plt.plot(xs_fiber, np.abs(Ez_fiber))
    # plt.xlabel("x (um)")
    # plt.ylabel("Ez (a.u.)")
    # plt.savefig("fiber.png")

    # M1, E-field
    # plt.figure(figsize=(10, 8), dpi=100)
    # plt.suptitle(
    #     "MEEP get_eigenmode / MPB find_modes / Lumerical (manual)",
    #     y=1.05,
    #     fontsize=18,
    # )

    # plt.subplot(2, 2, 1)
    # mode_waveguide.plot_ez(show=False, operation=np.abs, scale=False)

    # plt.subplot(2, 2, 2)
    # mode_fiber.plot_ez(show=False, operation=np.abs, scale=False)

    # plt.subplot(2, 2, 3)
    # mode_waveguide.plot_hz(show=False, operation=np.abs, scale=False)

    # plt.subplot(2, 2, 4)
    # mode_fiber.plot_hz(show=False, operation=np.abs, scale=False)

    # plt.tight_layout()
    # plt.show()

    # Plotting
    epsilons = [1, 1.43482, 1.44, 1.44427, 3.47]

    eps_parameters = {}
    eps_parameters["contour"] = True
    eps_parameters["levels"] = np.unique(epsilons)

    fiber_numerical_aperture = float(np.sqrt(1.44427 ** 2 - 1.43482 ** 2))

    sim_dict = get_simulation_fiber(
        # grating parameters
        period=0.66,
        fill_factor=0.5,
        n_periods=30,
        etch_depth=70 * nm,
        # fiber parameters,
        fiber_angle_deg=20.0,
        fiber_xposition=0.0,
        fiber_core_diameter=9,
        fiber_numerical_aperture=fiber_numerical_aperture,
        fiber_nclad=nSiO2,
        # material parameters
        ncore=3.47,
        ncladtop=1.44,
        ncladbottom=1.44,
        nsubstrate=3.47,
        # stack parameters
        pml_thickness=1.0,
        substrate_thickness=1.0,
        bottom_clad_thickness=2.0,
        core_thickness=220 * nm,
        top_clad_thickness=2.0,
        air_gap_thickness=1.0,
        fiber_thickness=2.0,
        # simulation parameters
        res=50,
    )
    plot(sim_dict["sim"], eps_parameters=eps_parameters)
    plt.show()
