import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="simmon",
    version="0.0.3",
    author="Roie Zemel",
    description="A simple simulation monitor",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    py_modules=["simmon"],
    package_dir={'': 'simmon'},
    install_requires=['matplotlib'],
    keywords=["simulation, data tracking"],
    license_files=('LICENSE',)
)
