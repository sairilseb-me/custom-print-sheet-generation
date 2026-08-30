"""Packaging entry point -- PyInstaller must target this file, not
patch_pos/app.py directly, since running app.py as the top-level script
breaks its relative imports (there'd be no parent package)."""

from patch_pos.app import main

if __name__ == "__main__":
    main()
