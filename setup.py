#!/usr/bin/env python
from setuptools import setup

setup(
    name="tap-codat",
    version="1.0.0",
    description="Singer.io tap for extracting data from the Codat API",
    author="Stitch",
    url="http://singer.io",
    classifiers=["Programming Language :: Python :: 3 :: Only"],
    py_modules=["tap_codat"],
    install_requires=[
        "singer-python==6.8.0",
        "requests==2.34.2",
        "pendulum==3.2.0"
    ],
    extras_require={
        'dev': [
            'pylint',
            'parameterized',
            'pytest',
            'pytest-cov',
            'coverage',
        ]
      },
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
