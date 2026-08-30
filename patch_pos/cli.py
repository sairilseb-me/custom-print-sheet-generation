"""CLI entry point for exercising the compositing engine in isolation,
outside the pywebview shell -- see PROJECT_INSTRUCTIONS.md section 8,
step 2.

Example:
    python -m patch_pos.cli \\
        --template "/Volumes/MP-JLS/MP Templates/PATCH/A4-PATCH-TEMPLATE-NO MIRROR.psd" \\
        --shape rectangular \\
        --sources product1/3x2-images/1-image-template.psd product2/3x2-images/1-image-template.psd \\
        --output out.pdf
"""

import argparse
import sys

from psd_tools import PSDImage

from .compositor import composite_sheet, flatten_source_psd
from .pdf_export import export_pdf
from .slots import get_layout, load_template_layouts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", required=True, help="Path to the master template PSD")
    parser.add_argument("--shape", required=True, choices=["rectangular", "circular"])
    parser.add_argument(
        "--sources", required=True, nargs="+", help="Ordered list of source product PSD paths"
    )
    parser.add_argument("--output", required=True, help="Output PDF path")
    args = parser.parse_args(argv)

    template_psd = PSDImage.open(args.template)
    layouts = load_template_layouts(template_psd)
    layout = get_layout(layouts, args.shape)

    images = [flatten_source_psd(path) for path in args.sources]
    sheet = composite_sheet(layout, images)
    export_pdf(sheet, args.output)

    print(
        f"Wrote {args.output} "
        f"({sheet.width}x{sheet.height}px, {len(images)}/{layout.cap} slots used)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
