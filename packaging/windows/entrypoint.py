"""PyInstaller entry point, shared by onefile and onedir distributions."""

from multiprocessing import freeze_support

from nexus_ai.app import main

if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
