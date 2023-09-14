# ogdf-wheel - an OGDF release build packaged as ready-to-use python wheel.

This project uses [cibuildwheel](cibuildwheel.readthedocs.io) to build the [OGDF](github.com/ogdf/ogdf) library into a ready-to-use python package (called wheel) installable via `pip install ogdf-wheel`. Its mainly intended to be used with [`ogdf-python`](github.com/ogdf/ogdf-python) when you don't want to build the OGDF yourself or use a C++ package manager.

## Publishing new Releases

The CI does neither automatically build new OGDF versions nor directly publishes the results to [PyPi](https://pypi.org/project/ogdf-wheel/). To publish a new version, perform the following steps:

- Update the `/ogdf/` submodule in this repo to point to the latest release of the OGDF.
- Update the version number in `pyproject.toml`.
- Commit and push your changes to GitHub.
- Wait for the CI there to finish.
- Download the resulting `.whl` files.
- Use [`twine`](https://twine.readthedocs.io/en/stable/index.html) to upload the files to PyPi.
