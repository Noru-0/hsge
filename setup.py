from setuptools import setup, find_packages

setup(
    name="hsge",
    version="0.1.0",
    description="Hierarchical Graph Exploration with Skill Abstraction",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "numpy",
    ],
)
