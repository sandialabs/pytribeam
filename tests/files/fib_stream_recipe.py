# python standard libraries
from pathlib import Path
import sys

# 3rd party libraries
from PIL import Image as pil_img
import numpy as np
from skimage import filters, measure


def process_image(input_path: Path, output_path: Path):
    with pil_img.open(input_path) as test_img:
        # threshold
        fib_img = np.asarray(test_img)
        threshold = filters.threshold_otsu(fib_img)
        segmented = fib_img > threshold

    # label connected components
    labeled_img, num_features = measure.label(
        segmented,
        return_num=True,
        connectivity=1,
    )

    # find largest componet:
    largest = None
    max_size = 0
    for component in range(1, num_features + 1):
        size = np.sum(labeled_img == component)
        if size > max_size:
            max_size = size
            largest = component

    # mask largest component
    mask = labeled_img == largest

    # write out image
    mask = pil_img.fromarray(mask)
    mask.save(output_path)


if __name__ == "__main__":
    # Get input and output paths passed from the subprocess:
    input_path = Path(sys.argv[1])
    output_path = Path(sys.argv[2])

    # Process the image
    process_image(
        input_path=input_path,
        output_path=output_path,
    )
