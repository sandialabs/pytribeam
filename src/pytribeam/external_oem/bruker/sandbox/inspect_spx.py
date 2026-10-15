import xml.etree.ElementTree as ET
import numpy as np


def read_spx(path):
    tree = ET.parse(path)
    root = tree.getroot()

    def find_text(tag):
        elem = root.find(f".//{tag}")
        if elem is None or elem.text is None:
            raise ValueError(f"Missing tag: {tag}")
        return elem.text.strip()

    channel_count = int(find_text("ChannelCount"))
    calib_abs = float(find_text("CalibAbs"))
    calib_lin = float(find_text("CalibLin"))
    sigma_abs = float(find_text("SigmaAbs"))
    sigma_lin = float(find_text("SigmaLin"))

    # First RealTime/LifeTime in file should be fine for most uses,
    # but these tags may appear in multiple sections.
    realtime = int(find_text("RealTime"))
    lifetime = int(find_text("LifeTime"))

    channels_text = find_text("Channels")
    counts = np.fromstring(channels_text, sep=",", dtype=np.int64)

    if counts.size != channel_count:
        raise ValueError(
            f"ChannelCount={channel_count}, but parsed {counts.size} channel values"
        )

    energy_keV = calib_abs + np.arange(channel_count, dtype=np.float64) * calib_lin

    metadata = {
        "channel_count": channel_count,
        "calib_abs_keV": calib_abs,
        "calib_lin_keV_per_channel": calib_lin,
        "sigma_abs": sigma_abs,
        "sigma_lin": sigma_lin,
        "realtime_ms": realtime,
        "lifetime_ms": lifetime,
    }

    return energy_keV, counts, metadata


if __name__ == "__main__":
    path = r"C:\Users\apolon\Bruker\Test\python_created3.spx"
    energy_keV, counts, meta = read_spx(path)

    print(meta)
    print("Energy [0:5] keV:", energy_keV[:5])
    print("Counts [0:20]:", counts[:20])
    print("Counts sum:", counts.sum())
