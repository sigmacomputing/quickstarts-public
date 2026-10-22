#!/usr/bin/env python3
"""Write a validated, read-only source workbook inventory."""

import argparse
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from source_workbook import build_source_model, validate_source_model


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--out", required=True)
    parser.add_argument("--block-decisions")
    args = parser.parse_args(argv)
    output = Path(args.out)
    temporary = None
    try:
        source = Path(args.source)
        if output.resolve() == source.resolve() or (output.exists() and os.path.samefile(output, source)):
            raise ValueError("output path refers to the source workbook")
        model = build_source_model(args.source, block_decisions=args.block_decisions)
        validate_source_model(model, args.source)
        encoded = json.dumps(model, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        output.parent.mkdir(parents=True, exist_ok=True)
        if output.resolve() == source.resolve() or (output.exists() and os.path.samefile(output, source)):
            raise ValueError("output path refers to the source workbook")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent,
                                         prefix=output.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
        os.replace(temporary, output)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        print(f"source-workbook: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
