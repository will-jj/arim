"""
Toolbox of functions for ultrasonic testing/acoustics.
"""
# Only function that does not require any arim-specific logic should be put here.
# This module must be kept free of any arim dependencies because so that it could be used
# without arim.

import warnings

import numpy as np


class UtWarning(UserWarning):
    pass


def fmc(numelements):
    """
    Return all pairs of elements for a FMC.
    HMC as performed by Brain.

    Returns
    -------
    tx : ndarray [numelements^2]
        Transmitter for each scanline: 0, 0, ..., 1, 1, ...
    rx : ndarray
        Receiver for each scanline: 1, 2, ..., 1, 2, ...
    """
    numelements = int(numelements)
    elements = np.arange(numelements)

    # 0 0 0    1 1 1    2 2 2
    tx = np.repeat(elements, numelements)

    # 0 1 2    0 1 2    0 1 2
    rx = np.tile(elements, numelements)
    return tx, rx


def hmc(numelements):
    """
    Return all pairs of elements for a HMC.
    HMC as performed by Brain (rx >= tx)

    Returns
    -------
    tx : ndarray [numelements^2]
        Transmitter for each scanline: 0, 0, 0, ..., 1, 1, 1, ...
    rx : ndarray
        Receiver for each scanline: 0, 1, 2, ..., 1, 2, ...
    """
    numelements = int(numelements)
    elements = np.arange(numelements)

    # 0 0 0    1 1    2
    tx = np.repeat(elements, range(numelements, 0, -1))

    # 0 1 2    0 1    2
    rx = np.zeros_like(tx)
    take_n_last = np.arange(numelements, 0, -1)
    start = 0
    for n in take_n_last:
        stop = start + n
        rx[start:stop] = elements[-n:]
        start = stop
    return tx, rx


def infer_capture_method(tx, rx):
    """
    Infers the capture method from the indices of transmitters and receivers.

    Returns: 'hmc', 'fmc', 'unsupported'

    Parameters
    ----------
    tx : list
        One per scanline
    rx : list
        One per scanline

    Returns
    -------
    capture_method : string
    """
    numelements = max(np.max(tx), np.max(rx)) + 1
    assert len(tx) == len(rx)

    # Get the unique combinations tx/rx of the input.
    # By using set, we ignore the order of the combinations tx/rx.
    combinations = set(zip(tx, rx))

    # Could it be a HMC? Most frequent case, go first.
    # Remark: HMC can be made with tx >= rx or tx <= rx. Check both.
    tx_hmc, rx_hmc = hmc(numelements)
    combinations_hmc1 = set(zip(tx_hmc, rx_hmc))
    combinations_hmc2 = set(zip(rx_hmc, tx_hmc))

    if (len(tx_hmc) == len(tx)) and ((combinations == combinations_hmc1) or
                                         (combinations == combinations_hmc2)):
        return 'hmc'

    # Could it be a FMC?
    tx_fmc, rx_fmc = fmc(numelements)
    combinations_fmc = set(zip(tx_fmc, rx_fmc))
    if (len(tx_fmc) == len(tx)) and (combinations == combinations_fmc):
        return 'fmc'

    # At this point we are hopeless
    return 'unsupported'


def default_scanline_weights(tx, rx):
    """
    Scanline weights for TFM.

    Consider a scanline obtained by the transmitter i and the receiver j; this
    scanline is denoted (i,j). If the response matrix contains both (i, j) and (j, i),
    the corresponding scanline weight is 1. Otherwise, the scanline weight is 2.

    Example: for a FMC, all scanline weights are 1.
    Example: for a HMC, scanline weights for the pulse-echo scanlines are 1,
    scanline weights for the non-pulse-echo scanlines are 2.

    Remark: the function does not check if there are duplicated signals.

    Parameters
    ----------
    tx : list[int] or ndarray
        tx[i] is the index of the transmitter (between 0 and numelements-1) for
        the i-th scanline.
    rx : list[int] or ndarray
        rx[i] is the index of the receiver (between 0 and numelements-1) for
        the i-th scanline.

    Returns
    -------
    scanline_weights : ndarray

    """
    if len(tx) != len(rx):
        raise ValueError('tx and rx must have the same lengths (numscanlines)')
    numscanlines = len(tx)

    # elements_pairs contains (tx[0], rx[0]), (tx[1], rx[1]), etc.
    elements_pairs = {*zip(tx, rx)}
    scanline_weights = np.ones(numscanlines)
    for this_tx, this_rx, scanline_weight in \
            zip(tx, rx, np.nditer(scanline_weights, op_flags=['readwrite'])):
        if (this_rx, this_tx) not in elements_pairs:
            scanline_weight[...] = 2.
    return scanline_weights


def decibel(arr, reference=None, neginf_value=-1000., return_reference=False):
    """
    Return 20*log10(abs(arr) / reference)

    If reference is None, use:

        reference := max(abs(arr))

    Parameters
    ----------
    arr : ndarray
        Values to convert in dB.
    reference : float or None
        Reference value for 0 dB. Default: None
    neginf_value : float or None
        If not None, convert -inf dB values to this parameter. If None, -inf
        dB values are not changed.
    return_max : bool
        Default: False.

    Returns
    -------
    arr_db
        Array in decibel.
    arr_max: float
        Return ``max(abs(arr))``. This value is returned only if return_max is true.

    """
    # Disable warnings messages for log10(0.0)
    arr_abs = np.abs(arr)

    if arr_abs.shape == ():
        orig_shape = ()
        arr_abs = arr_abs.reshape((1,))
    else:
        orig_shape = None

    if reference is None:
        reference = np.nanmax(arr_abs)
    else:
        assert reference > 0.

    with np.errstate(divide='ignore'):
        arr_db = 20 * np.log10(arr_abs / reference)

    if neginf_value is not None:
        arr_db[np.isneginf(arr_db)] = neginf_value

    if orig_shape is not None:
        arr_db = arr_db.reshape(orig_shape)

    if return_reference:
        return arr_db, reference
    else:
        return arr_db


def wrap_phase(phases):
    """Return a phase in [-pi, pi[

    http://stackoverflow.com/questions/15927755/opposite-of-numpy-unwrap
    """
    phases = np.asarray(phases)
    return (phases + np.pi) % (2 * np.pi) - np.pi


def instantaneous_phase_shift(analytic_sig, time_vect, carrier_frequency):
    """
    For a signal $x(ray) = A * exp(i (2 pi f_0 ray + phi(ray)))$, returns phi(ray) in [-pi, pi[.

    Parameters
    ----------
    analytic_sig: ndarray
    time_vect: ndarray
    carrier_frequency: float

    Returns
    -------
    phase_shift

    """
    analytic_sig = np.asarray(analytic_sig)
    dtype = analytic_sig.dtype
    if dtype.kind != 'c':
        warnings.warn('Expected an analytic (complex) signal, got {}. Use a Hilbert '
                      'transform to get the analytic signal.'.format(dtype), UtWarning,
                      stacklevel=2)
    phase_correction = 2 * np.pi * carrier_frequency * time_vect
    phase = wrap_phase(np.angle(analytic_sig) - phase_correction)
    return phase


def make_timevect(num, step, start=0., dtype=None):
    """
    Return a linearly spaced time vector.

    Remark: using this method is preferable to ``numpy.arange(start, start + num * step, step``
    which may yield an incorrect number of samples due to numerical inaccuracy.

    Parameters
    ----------
    num : int
        Number of samples to generate.
    step : float, optional
        Time step (time between consecutive samples).
    start : scalar
        Starting value of the sequence. Default: 0.
    dtype : numpy.dtype
        Optional, the type of the output array.  If `dtype` is not given, infer the data
        type from the other input arguments.

    Returns
    -------
    samples : ndarray
        Linearly spaced vector ``[start, stop]`` where ``end = start + (num - 1)*step``

    Examples
    --------
    >>> make_timevect(10, .1)
    array([ 0. ,  0.1,  0.2,  0.3,  0.4,  0.5,  0.6,  0.7,  0.8,  0.9])
    >>> make_timevect(10, .1, start=1.)
    array([ 1. ,  1.1,  1.2,  1.3,  1.4,  1.5,  1.6,  1.7,  1.8,  1.9])

    Notes
    -----

    Adapted from ``numpy.linspace``
    (License: http://www.numpy.org/license.html ; 3 clause BSD)

    """
    if not isinstance(num, int):
        raise TypeError('num must be an integer (got {})'.format(type(num)))
    if num < 0:
        raise ValueError("Number of samples, %s, must be non-negative." % num)

    # Convert float/complex array scalars to float
    start = start * 1.
    step = step * 1.

    dt = np.result_type(start, step)
    if dtype is None:
        dtype = dt

    y = np.arange(0, num, dtype=dt)

    if num > 1:
        y *= step

    y += start

    return y.astype(dtype, copy=False)


