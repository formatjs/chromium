"""Compatibility imports for the overlay PCH validator."""

from pathlib import Path
import runpy

_validator = runpy.run_path(str(Path(__file__).resolve().parents[3] /
                               'overlays/chromium/bcr/overlay/native/pch_validate.py'))
project_path = _validator['project_path']
validate = _validator['validate']
main = _validator['main']

if __name__ == '__main__':
    main()
