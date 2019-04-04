import numpy as np
import pytest
import math

import arim
import arim.im as im
import arim.im.tfm, arim.ray
import arim.io
import arim.geometry as g


def test_extrema_lookup_times_in_rectbox():
    grid = g.Grid(-10.0, 10.0, 0.0, 0.0, 0.0, 15.0, 1.0)
    tx = [0, 0, 0, 1, 1, 1]
    rx = [0, 1, 2, 1, 1, 2]

    lookup_times_tx = np.zeros((grid.numpoints, len(tx)))
    lookup_times_rx = np.zeros((grid.numpoints, len(tx)))

    # scanline 5 (tx=1, rx=2) is the minimum time:
    grid_idx = 5
    lookup_times_tx[grid_idx, 5] = -1.5
    lookup_times_rx[grid_idx, 5] = -1.5
    # some noise:
    lookup_times_tx[grid_idx, 4] = -2.0
    lookup_times_rx[grid_idx, 4] = -0.1

    # scanline 1 (tx=0, rx=1) is the maximum time:
    grid_idx = 3
    lookup_times_tx[grid_idx, 1] = 1.5
    lookup_times_rx[grid_idx, 1] = 1.5
    # some noise:
    lookup_times_tx[0, 0] = 2.0
    lookup_times_rx[0, 0] = 0.1

    out = im.tfm.extrema_lookup_times_in_rectbox(
        grid, lookup_times_tx, lookup_times_rx, tx, rx
    )
    assert math.isclose(out.tmin, -3.0)
    assert math.isclose(out.tmax, 3.0)
    assert out.tx_elt_for_tmin == 1
    assert out.rx_elt_for_tmin == 2
    assert out.tx_elt_for_tmax == 0
    assert out.rx_elt_for_tmax == 1


@pytest.mark.parametrize("use_real_grid", [True, False])
def test_multiview_tfm(use_real_grid):
    # make probe
    probe = arim.Probe.make_matrix_probe(5, 0.5e-3, 1, np.nan, 1e6)
    probe.set_reference_element("first")
    probe.reset_position()
    probe.translate([0.0, 0.0, -1e-3])

    # make frame
    tx_arr, rx_arr = arim.ut.fmc(probe.numelements)
    time = arim.Time(0.5e-6, 1 / 20e6, 100)
    # use random data but ensure reciprocity
    scanlines = np.zeros((len(tx_arr), len(time)))
    for i, (tx, rx) in enumerate(zip(tx_arr, rx_arr)):
        np.random.seed((tx * rx) ** 2)  # symmetric in tx and rx
        scanlines[i] = np.random.rand(len(time))
    block = arim.Material(6300, 3100)
    frame = arim.Frame(
        scanlines, time, tx_arr, rx_arr, probe, arim.ExaminationObject(block)
    )

    # prepare view LL-T in contact
    if use_real_grid:
        grid = arim.Grid(0.0, 0.0, 0.0, 0.0, 5e-3, 5e-3, np.nan)
        grid_interface = arim.Interface(*grid.to_oriented_points())
    else:
        grid = arim.Points(np.array([0.0, 0.0, 5e-3]), name="Grid")
        grid_interface = arim.Interface(
            *arim.geometry.default_oriented_points(grid.to_1d_points())
        )

    backwall = arim.geometry.points_1d_wall_z(-1e-3, 1e-3, 10e-3, 200)
    backwall_interface = arim.Interface(*backwall)
    probe_interface = arim.Interface(*probe.to_oriented_points())

    path_LL = arim.Path(
        [probe_interface, backwall_interface, grid_interface],
        [block, block],
        ["L", "L"],
    )
    path_T = arim.Path([probe_interface, grid_interface], [block], ["T"])
    view = arim.View(path_LL, path_T, "LL-T")
    arim.ray.ray_tracing([view], convert_to_fortran_order=True)

    # make TFM
    tfm = im.tfm.tfm_for_view(frame, grid, view, fillvalue=np.nan)

    # Check this value is unchanged over time!
    expected_val = 12.745499105785953 / frame.numscanlines
    assert tfm.res.shape == grid.shape
    if use_real_grid:
        np.testing.assert_array_almost_equal(tfm.res, [[[expected_val]]])
    else:
        np.testing.assert_allclose(tfm.res, expected_val)

    # Reverse view
    view_rev = arim.View(path_LL, path_T, "T-LL")
    tfm_rev = im.tfm.tfm_for_view(frame, grid, view_rev, fillvalue=np.nan)
    assert tfm.res.shape == grid.shape
    if use_real_grid:
        np.testing.assert_array_almost_equal(tfm_rev.res, [[[expected_val]]])
    else:
        np.testing.assert_allclose(tfm_rev.res, expected_val)


@pytest.mark.parametrize("use_hmc", [False, True])
def test_contact_tfm(use_hmc):
    # make probe
    probe = arim.Probe.make_matrix_probe(5, 0.5e-3, 1, np.nan, 1e6)
    probe.set_reference_element("first")
    probe.reset_position()
    probe.translate([0.0, 0.0, -1e-3])

    # make frame
    if use_hmc:
        tx_arr, rx_arr = arim.ut.hmc(probe.numelements)
    else:
        tx_arr, rx_arr = arim.ut.fmc(probe.numelements)

    time = arim.Time(0.5e-6, 1 / 20e6, 100)

    # use random data but ensure reciprocity
    scanlines = np.zeros((len(tx_arr), len(time)))
    for i, (tx, rx) in enumerate(zip(tx_arr, rx_arr)):
        np.random.seed((tx * rx) ** 2)  # symmetric in tx and rx
        scanlines[i] = np.random.rand(len(time))

    # check reciprocity
    if not use_hmc:
        for i, (tx, rx) in enumerate(zip(tx_arr, rx_arr)):
            scanline_1 = scanlines[i]
            scanline_2 = scanlines[np.logical_and(tx_arr == rx, rx_arr == tx)][0]
            np.testing.assert_allclose(
                scanline_1, scanline_2, err_msg="fmc data not symmetric"
            )

    block = arim.Material(6300, 3100)
    frame = arim.Frame(
        scanlines, time, tx_arr, rx_arr, probe, arim.ExaminationObject(block)
    )

    # prepare view LL-T in contact
    grid = arim.Points(np.array([0.0, 0.0, 5e-3]), name="Grid")

    tfm = im.tfm.contact_tfm(frame, grid, block.longitudinal_vel, fillvalue=np.nan)

    # Check this value is unchanged over time!
    expected_val = 12.49925772283528 / frame.numscanlines
    assert tfm.res.shape == grid.shape
    np.testing.assert_allclose(tfm.res, expected_val)
