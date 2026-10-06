from setuptools import setup, find_packages

setup(
    name="pbs-link",
    version="0.1.3",
    description="Reference SDK for the Pale Blue Systems Protocol (PBS-ENV-01 v1.5)",
    author="Pale Blue Systems Foundation",
    url="https://github.com/Pale-Blue-Systems/PBS_LINK",
    packages=find_packages(),
    install_requires=[],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Topic :: System :: Networking",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
    ],
    python_requires='>=3.8',
)