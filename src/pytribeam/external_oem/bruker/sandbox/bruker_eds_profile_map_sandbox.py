import sys
import traceback
from datetime import datetime
from pathlib import Path

# Adjust this for your checkout layout
REPO_ROOT = Path(__file__).resolve().parents[5]
SRC_ROOT = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from pytribeam.external_oem.bruker.eds import BrukerEDSController
from pytribeam.external_oem.bruker.session import BrukerSession
from pytribeam.external_oem.bruker.types import (
    BrukerEDSElementMapSetting,
    BrukerEDSProfileMapSettings,
    BrukerSessionSettings,
)

OUT_DIR = Path(r"C:\Users\apolon\Documents\Polonsky\BrukerSandbox")
OUT_DIR.mkdir(parents=True, exist_ok=True)

STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_PATH = OUT_DIR / f"eds_profile_map_sandbox_{STAMP}.log"
BCF_PATH = OUT_DIR / f"eds_profile_map_{STAMP}.bcf"
BMP_PATH = OUT_DIR / f"eds_profile_map_{STAMP}.bmp"


def log(msg: str):
    line = f"[{datetime.now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    log("=== Bruker EDS profile map sandbox start ===")
    log(f"Log path: {LOG_PATH}")
    log(f"BCF output: {BCF_PATH}")
    log(f"BMP output: {BMP_PATH}")

    session_settings = BrukerSessionSettings(
        dll_dir=r"C:\Program Files\Bruker\Esprit API",
        mode="local",
        server="Lokaler Server",
        user="edx",
        password="edx",
        host=None,
        port=None,
        close_on_exit=False,
        keep_connection_open=True,
    )

    session = None

    try:
        session = BrukerSession(session_settings)
        info = session.connect()
        log(f"Connected with CID={info.cid}")
        log("QueryInfo:")
        for line in info.query_info.splitlines():
            log(f"  {line}")

        eds = BrukerEDSController(session)

        settings = BrukerEDSProfileMapSettings(
            name="eds_profile_map_sandbox",
            width_px=64,
            height_px=48,
            pixel_time_us=1024,
            output_bcf_path=str(BCF_PATH),
            output_image_path=str(BMP_PATH),
            output_image_format="bmp",
            spu_device=1,
            elements=(
                # Example elements. Adjust for your sample.
                BrukerEDSElementMapSetting(
                    atomic_number=14,  # Si
                    line="KA",
                    energy_keV=0.0,
                    width=1.0,
                    # display_rgb=(0, 255, 0),
                ),
                BrukerEDSElementMapSetting(
                    atomic_number=26,  # Fe
                    line="KA",
                    energy_keV=0.0,
                    width=1.0,
                    # display_rgb=(0, 0, 255),
                ),
                BrukerEDSElementMapSetting(
                    atomic_number=13,  # Al
                    line="KA",
                    energy_keV=0.0,
                    width=1.0,
                    # display_rgb=(0, 0, 255),
                ),
            ),
            image_filter=0,
            map_filter=0,
            map_filter_width=3,
            color_mix_method=0,
            brightness=0.0,
            gamma=1.0,
            color_saturation=1.0,
            absolute_scaling=False,
            normalization=True,
            deconvolution=False,
        )

        log(f"Profile map settings: {settings}")

        log("Creating profile XML for diagnostic preview")
        profile_xml = eds.create_hymap_profile(settings)
        log(f"Profile XML length: {len(profile_xml)}")
        log(f"Profile XML preview: {profile_xml[:500]}")
        for token in ["Element", "KA", "255", "Color", "14", "26"]:
            log(f"Profile XML contains {token!r}: {token in profile_xml}")

        log("Starting profile-based EDS map acquisition")
        outputs = eds.acquire_map_with_profile(
            settings=settings,
            poll_interval_s=0.5,
            max_wait_s=600.0,
        )
        log(f"Profile map outputs: {outputs}")

        log("Exporting element images by index for diagnostics")

        # Try a few indices intentionally, because Bruker element indexing may
        # include image channel / internal offset behavior.
        for idx in range(0, len(settings.elements) + 2):
            try:
                elem_path = OUT_DIR / f"eds_profile_map_{STAMP}_element_index_{idx}.bmp"
                saved = eds.save_element_image(
                    output_path=str(elem_path),
                    element_index=idx,
                    fmt="bmp",
                )
                log(
                    f"Element image index {idx} saved: {saved} size={elem_path.stat().st_size}"
                )
                with open(elem_path, "rb") as f:
                    log(f"Element image index {idx} magic: {f.read(2)!r}")
            except Exception as exc:
                log(f"Element image index {idx} export failed: {exc}")

        try:
            mixed_path = OUT_DIR / f"eds_profile_map_{STAMP}_mixed.bmp"
            saved = eds.save_mixed_map_image(
                output_path=str(mixed_path),
                fmt="bmp",
            )
            log(f"Mixed map image saved: {saved} size={mixed_path.stat().st_size}")
            with open(mixed_path, "rb") as f:
                log(f"Mixed map magic: {f.read(2)!r}")
        except Exception as exc:
            log(f"Mixed map image export failed: {exc}")

        log("Exporting raw element data byte lengths for diagnostics")
        for idx in range(0, len(settings.elements) + 2):
            try:
                data = eds.get_element_data_bytes(element_index=idx)
                log(
                    f"Element data index {idx}: byte length={len(data)} first16={data[:16]!r}"
                )
            except Exception as exc:
                log(f"Element data index {idx} failed: {exc}")

        if BCF_PATH.exists():
            log(f"BCF exists: {BCF_PATH} size={BCF_PATH.stat().st_size}")
        else:
            log("BCF missing")

        if BMP_PATH.exists():
            log(f"BMP exists: {BMP_PATH} size={BMP_PATH.stat().st_size}")
            with open(BMP_PATH, "rb") as f:
                log(f"BMP magic: {f.read(2)!r}")
        else:
            log("BMP missing")

        log("Exporting parsed numeric element arrays for diagnostics")
        for idx in range(0, len(settings.elements) + 2):
            try:
                arr = eds.get_element_data_array(
                    element_index=idx,
                    width_px=settings.width_px,
                    height_px=settings.height_px,
                    dtype="uint16",
                )
                log(
                    f"Element array index {idx}: "
                    f"shape={arr.shape}, dtype={arr.dtype}, "
                    f"min={arr.min()}, max={arr.max()}, "
                    f"sum={int(arr.sum())}, nonzero={int((arr != 0).sum())}"
                )
            except Exception as exc:
                log(f"Element array index {idx} failed: {exc}")

        log("Saving numeric EDS element maps as .npy")
        try:
            npy_paths = eds.save_profile_element_maps_npy(
                settings=settings,
                output_dir=str(OUT_DIR),
                prefix=f"eds_profile_map_{STAMP}",
                dtype="uint16",
            )
            for path in npy_paths:
                log(f"Saved element map .npy: {path}")
        except Exception as exc:
            log(f"Saving element map .npy files failed: {exc}")

        log("EDS profile map sandbox complete")

    except Exception as exc:
        log(f"ERROR: {exc}")
        tb = traceback.format_exc()
        for line in tb.splitlines():
            log(line)

    finally:
        if session is not None:
            log("Leaving Esprit connection open (close_on_exit=False)")
        log("=== Bruker EDS profile map sandbox end ===")


if __name__ == "__main__":
    main()
