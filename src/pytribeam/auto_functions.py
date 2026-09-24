from statistics import mean
import time
from typing import NamedTuple, Tuple

from scipy.ndimage import sobel, gaussian_filter
import numpy as np
import math
from PIL import Image
from scipy.optimize import minimize_scalar
import matplotlib.pyplot as plt
from scipy.stats import stats
from scipy.signal import find_peaks
from scipy.stats import norm
from scipy.optimize import curve_fit

import pytribeam.types as tbt
import pytribeam.utilities as ut

try:
    from autoscript_sdb_microscope_client import SdbMicroscopeClient
    from autoscript_sdb_microscope_client import enumerations as enums
    from autoscript_sdb_microscope_client import structures as structs

    RESOLUTION_PRESETS = {
        6144: enums.ScanningResolution.PRESET_6144X4096,
        3072: enums.ScanningResolution.PRESET_3072X2048,
        1536: enums.ScanningResolution.PRESET_1536X1024,
        768: enums.ScanningResolution.PRESET_768X512,
    }
except ImportError:
    SdbMicroscopeClient = object
    enums = None
    structs = None
    RESOLUTION_PRESETS = {}


class Autofocus:
    def __init__(
        self,
        microscope: SdbMicroscopeClient = None,
        res=1536,
        hfw_large=1e-3,
        dwell=1e-6,
        simulating=False,
        image_path="simulated_image/test.tif",
        n_points_LR_LHFW=3,
        n_points_LR_SHFW=3,
        n_points_LS_LHFW=3,
        n_points_LS_SHFW=3,
        max_iterations=15,
        tolerance=1e-5,
        bit_depth=8,
        beam="electron",
        testing=False,
        do_gaussian_fit=True,
        hfw_small=20e-6,
    ):
        self.microscope = microscope
        self.res = res
        self.hfw_large = hfw_large
        self.dwell = dwell
        self.simulating = simulating
        self.image_path = image_path
        self.n_points_LR_LHFW = n_points_LR_LHFW
        self.n_points_LR_SHFW = n_points_LR_SHFW
        self.n_points_LS_LHFW = n_points_LS_LHFW
        self.n_points_LS_SHFW = n_points_LS_SHFW
        self.max_iterations = max_iterations
        self.tolerance = tolerance
        self.bit_depth = bit_depth
        self.beam = beam
        self.testing = testing
        self.do_gaussian_fit = do_gaussian_fit
        self.hfw_small = hfw_small
        self._testing_wds: list = []
        self._testing_iqs: list = []

    def set_simulating(self, simulating):
        self.simulating = simulating
        return self

    def _beam(self, beam=None):
        beam = (beam or self.beam).lower()
        if beam == "electron":
            return self.microscope.beams.electron_beam
        if beam == "ion":
            return self.microscope.beams.ion_beam
        raise ValueError(f"Invalid beam: {beam}. Use 'electron' or 'ion'.")

    def _resolve_resolution(self, resolution):
        if resolution is None:
            return None
        if isinstance(resolution, float):
            resolution = int(resolution)
        elif isinstance(resolution, str):
            resolution = int(resolution.strip())
        if resolution in RESOLUTION_PRESETS:
            return RESOLUTION_PRESETS[resolution]
        raise ValueError(
            f"Invalid resolution: {resolution}. Use one of {sorted(RESOLUTION_PRESETS)}."
        )

    ######################### Microscope Imaging Controls #########################

    def get_resolution(self, beam=None):
        string = self._beam(beam).scanning.resolution.value
        x_res = self._beam(beam).scanning.resolution.width
        y_res = self._beam(beam).scanning.resolution.height
        return x_res, y_res

    def set_resolution(self, resolution, beam=None):
        resolved = self._resolve_resolution(resolution)
        self._beam(beam).scanning.resolution.value = resolved
        time.sleep(0.5)

    def get_dwell(self, beam=None):
        return self._beam(beam).scanning.dwell_time.value

    def set_dwell(self, dwell_time, beam=None):
        self._beam(beam).scanning.dwell_time.value = dwell_time

    def get_hfw(self, beam=None):
        return self._beam(beam).horizontal_field_width.value

    def set_hfw(self, hfw, beam=None):
        self._beam(beam).horizontal_field_width.value = hfw

    def get_wd(self, beam=None):
        return self._beam(beam).working_distance.value

    def set_wd(self, wd, beam=None):
        self._beam(beam).working_distance.set_value_no_degauss(wd)
        # time.sleep(0.01)

    def set_reduced_area(self):
        reduced_area = (0.25, 0.25, 0.5, 0.5)
        self._beam().scanning.mode.set_reduced_area(*reduced_area)

    def grab_frame(self, bit_depth=None):
        bit_depth = self.bit_depth if bit_depth is None else bit_depth
        frame = self.microscope.imaging.grab_frame(
            structs.GrabFrameSettings(bit_depth=bit_depth)
        )
        return np.copy(frame.data)

    def get_image(self, wd):
        self.set_resolution(self.res, beam=self.beam)
        time.sleep(0.1)
        image_time = self.get_resolution()[0] * self.get_resolution()[1] * self.dwell
        print(f"Estimated image time: {image_time} s")
        t0 = time.perf_counter()
        self.set_wd(wd)
        self.set_dwell(self.dwell)
        self.set_hfw(self.hfw_large)
        self.set_resolution(self.res)
        time.sleep(0.1)
        t1 = time.perf_counter()
        time.sleep(image_time + 0.1 * image_time)
        frame = self.microscope.imaging.get_image()
        frame = frame.data
        t2 = time.perf_counter()
        print(f"        set_wd={t1-t0:.3f}s  grab_frame={t2-t1:.3f}s")
        return frame

    def compute_metric(self, image):
        """Compute the sharpness metric from an already-acquired image."""
        return self.sobel_variance(image)

    def get_metric(self, wd, simulating=None):
        if simulating is None:
            simulating = self.simulating
        image = self.get_image(wd)
        metric = self.compute_metric(image)
        if self.testing:
            self._testing_wds.append(wd)
            self._testing_iqs.append(metric)
        return metric

    def prominence_metric(self, iqs):
        iqs = np.asarray(iqs, dtype=float)
        mean_iq = np.mean(iqs)
        if mean_iq == 0:
            return 0.0
        return float(np.max(iqs) / mean_iq)

    def get_background(self, bounds):
        """Grab 5 images within the bounds to get a background sharpness value."""
        _eval_count = [0]

        # Grab image
        image_time = self.get_resolution()[0] * self.get_resolution()[1] * self.dwell
        print(f"Estimated image time: {image_time} s")

        _eval_count[0] += 1
        t0 = time.perf_counter()

        # Empty metric list to append to
        metrics = []

        for wd in np.linspace(bounds[0], bounds[1], 5):
            print(
                f"    [iter {_eval_count[0]}] WD = {wd * 1e3:.4f} mm ...",
                end=" ",
                flush=True,
            )
            m = self.get_metric(wd)
            metrics.append(m)
            print(f"sharpness = {m:.4f}  ({time.perf_counter() - t0:.3f} s)")

        return np.average(metrics)

    def convergent_search(self, bounds, max_iterations=15, tolerance=0.001):
        print(
            f"  Convergent search in [{bounds[0]*1e3:.4f}, {bounds[1]*1e3:.4f}] mm "
            f"(tol={tolerance*1e3:.4f} mm, max_iter={max_iterations}) ..."
        )

        _eval_count = [0]
        _history = []  # (wd, metric)

        image_time = self.get_resolution()[0] * self.get_resolution()[1] * self.dwell
        print(f"Estimated image time: {image_time} s")

        def _neg_metric(wd):
            _eval_count[0] += 1
            t0 = time.perf_counter()
            print(
                f"    [iter {_eval_count[0]}] WD = {wd*1e3:.4f} mm ...",
                end=" ",
                flush=True,
            )
            m = self.get_metric(wd)
            print(f"sharpness = {m:.4f}  ({time.perf_counter()-t0:.3f} s)")
            _history.append((wd, m))
            return -m

        t_conv_start = time.perf_counter()

        # If the result is within the bounds, just return the result
        result = minimize_scalar(
            _neg_metric,
            bounds=bounds,
            method="bounded",
            options={"xatol": tolerance, "maxiter": max_iterations},
        )

        lower_bound = bounds[0]
        upper_bound = bounds[1]
        diff = upper_bound - lower_bound
        lbd = math.isclose(result.x, lower_bound, rel_tol=0.05 * lower_bound)
        upd = math.isclose(result.x, upper_bound, rel_tol=0.05 * upper_bound)
        count = 0

        while (lbd or upd) and count <= 1:
            print(
                f"Warning: Optimal WD is on the boundary of search inputs. Expanding search."
            )

            if lbd:
                lower_bound = lower_bound - 0.75 * diff
                upper_bound = upper_bound - 0.75 * diff

                bounds = [lower_bound, upper_bound]

                print(
                    f"Convergent search in [{bounds[0]*1e3:.4f}, {bounds[1]*1e3:.4f}] mm{bounds}"
                )

                # Do the search again
                result = minimize_scalar(
                    _neg_metric,
                    bounds=bounds,
                    method="bounded",
                    options={"xatol": tolerance, "maxiter": max_iterations},
                )

            if upd:
                lower_bound = lower_bound + 0.75 * diff
                upper_bound = upper_bound + 0.75 * diff

                bounds = [lower_bound, upper_bound]

                print(
                    f"Convergent search in [{bounds[0] * 1e3:.4f}, {bounds[1] * 1e3:.4f}] mm{bounds}"
                )

                # Do the search again
                result = minimize_scalar(
                    _neg_metric,
                    bounds=bounds,
                    method="bounded",
                    options={"xatol": tolerance, "maxiter": max_iterations},
                )

            # Only expand the bounds once
            count += 1

        # ###### Insert some code that will check that the result is sufficiently above background ######
        # bg = self.get_background(bounds)
        # print(bg)
        # peak = result.x
        # if peak >= 1.5 * bg:
        #     print(f"Sharpness peak is 1.5 times background.")
        # else:
        #     print(
        #         f"Sharpness peak is not 1.5 times background. Image clarity may be unsatisfactory."
        #     )

        ##### Some stuff that can be gotten rid of probably #####
        best5 = sorted(_history, key=lambda p: p[1], reverse=True)[: len(_history)]
        best5_wds, best5_iqs = zip(*best5) if best5 else ((), ())

        print(
            f"Convergent search done in {time.perf_counter()-t_conv_start:.3f} s.  "
            f"Best WD = {result.x*1e3:.4f} mm"
        )
        return result.x, best5_wds, best5_iqs

    ######################### Algorithm Logic #########################

    def find_optimal_wd(self, bounds):
        """Run the staged optimizer, set the result on the microscope, and return it."""
        if self.testing:
            self._testing_wds.clear()
            self._testing_iqs.clear()

        self.microscope.imaging.start_acquisition()

        print(
            f"Starting autofocus search in "
            f"[{bounds[0]*1e3:.3f}, {bounds[1]*1e3:.3f}] mm ..."
        )
        t_total_start = time.perf_counter()

        # Use the convergent search to find the optimized working distance
        wd, best5wds, best5iqs = self.convergent_search(
            bounds,
            max_iterations=self.max_iterations,
            tolerance=self.tolerance,
        )

        if not self.simulating:
            print(f"\nSetting WD to {wd*1e3:.4f} mm on microscope ...")
            self.set_wd(wd)
        print(
            f"\nAutofocus finished in {time.perf_counter()-t_total_start:.3f} s.  "
            f"Optimal WD = {wd*1e3:.4f} mm"
        )

        self.set_wd(wd)

        self.microscope.imaging.stop_acquisition()

        if self.testing:
            self._plot_testing(wd, bounds)
        return wd

    def _plot_testing(self, optimal_wd, bounds):
        """Plot all sampled WD vs sharpness metric (only called when testing=True)."""
        wds_mm = np.array(self._testing_wds) * 1e3
        iqs = np.array(self._testing_iqs)

        fig, ax = plt.subplots(figsize=(9, 4))
        ax.scatter(wds_mm, iqs, zorder=5, label="Sampled points", color="steelblue")
        ax.axvline(
            optimal_wd * 1e3,
            color="red",
            linestyle="--",
            label=f"Optimal WD = {optimal_wd*1e3:.4f} mm",
        )
        ax.axvspan(
            bounds[0] * 1e3,
            bounds[1] * 1e3,
            alpha=0.08,
            color="gray",
            label="Search range",
        )
        ax.set_xlabel("Working Distance (mm)")
        ax.set_ylabel("Sharpness Metric (Sobel Variance)")
        ax.set_title("Autofocus: WD vs Sharpness Metric")
        ax.legend()
        fig.tight_layout()
        plt.show()

    ######################### Image Quality Metrics #########################

    def sobel_variance(self, image):
        image = image.astype(np.float64)
        sobel_x = sobel(image, axis=0)
        sobel_y = sobel(image, axis=1)
        variance = np.var(np.hypot(sobel_x, sobel_y))
        return variance

    def std(self, image):
        image = image.astype(np.float64)
        return np.std(image)

    def FFT_power_above_thresh(self, image, freq_thresh=0.1):
        """High-frequency energy fraction. freq_thresh in cycles/pixel, in (0, 0.5)."""
        image = image.astype(np.float64)
        image = image - image.mean()  # reduces DC dominance before normalize
        power = np.abs(np.fft.fft2(image)) ** 2
        power /= power.sum()  # normalize so all coefficients sum to 1
        fy = np.fft.fftfreq(image.shape[0])  # cycles/pixel
        fx = np.fft.fftfreq(image.shape[1])
        radius = np.sqrt(fy[:, None] ** 2 + fx[None, :] ** 2)
        return 1 / power[radius > freq_thresh].sum()


class AutoFocusSettings(NamedTuple):
    bounds: Tuple
    beam: str
    res: int
    hfw_large: float
    dwell: float
    tolerance: float
    testing: bool
    gaussian_fit: bool


def run_autofocus(
    settings: AutoFocusSettings, microscope: tbt.Microscope, guess_wd_m: float
) -> float:
    af = Autofocus(
        microscope=microscope,
        beam=settings.beam,
        res=settings.res,
        hfw_large=settings.hfw_large,
        # hfw_small=hfw_small,
        dwell=settings.dwell,
        simulating=True,
        tolerance=settings.tolerance,
        testing=settings.testing,
        do_gaussian_fit=settings.gaussian_fit,
    )

    print(
        f"Searching WD in [{settings.bounds[0]*1e3:.3f}, {settings.bounds[1]*1e3:.3f}] mm ..."
    )
    optimal_wd = af.find_optimal_wd(settings.bounds)

    # time.sleep(2)
    microscope.imaging.start_acquisition()

    af.set_wd(wd=guess_wd_m)
    guess_metric = af.get_metric(wd=guess_wd_m)
    microscope.imaging.start_acquisition()
    af.set_wd(wd=optimal_wd)
    optimal_metric = af.get_metric(wd=optimal_wd)

    microscope.imaging.stop_acquisition()

    print(
        f"\nAutofocus complete. "
        f"\tOptimal WD: {optimal_wd * 1e3:.3f} mm with metric of {optimal_metric}"
        f"\tGuess WD: {guess_wd_m * 1e3:.3f} mm with metric of {guess_metric}"
    )

    if guess_metric < optimal_metric:
        return optimal_wd
    return guess_wd_m
