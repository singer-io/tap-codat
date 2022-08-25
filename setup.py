#!/usr/bin/env python
from setuptools import setup

setup(
    name="tap-codat",
    version="0.5.2",
    description="Singer.io tap for extracting data from the Codat API",
    author="Stitch",
    url="http://singer.io",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_codat"],
    install_requires=[
        "singer-python==5.8.1",
        "requests==2.20.0",
        "pendulum==1.2.0"
    ],
    entry_points="""
    [console_scripts]
    tap-codat=tap_codat:main
    """,
    packages=["tap_codat"],
    package_data = {
        "schemas": ["tap_codat/schemas/*.json"]
    },
    include_package_data=True,
)
