import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="simple-simon",                           # This is the name of the package
    version="0.0.2",                               # The initial release version
    author="Roie Zemel",                           # Full name of the author
    description="A simple simulation monitor",
    long_description=long_description,             # Long description read from the the readme file
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),           # List of all python modules to be installed
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],                                             # Information to filter the project on PyPi website
    python_requires='>=3.6',                       # Minimum version requirement of the package
    py_modules=["simon"],                          # Name of the python package
    package_dir={'':'simon'},                      # Directory of the source code of the package
    install_requires=['matplotlib']                # Install other dependencies if any
)