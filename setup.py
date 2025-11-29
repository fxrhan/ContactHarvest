from setuptools import setup, find_packages

setup(
    name="contactharvest",
    version="1.0.0",
    description="Advanced async web crawler to extract emails, phone numbers, and social media links from websites",
    author="fxrhan",
    url="https://github.com/fxrhan/ContactHarvest-.git",
    packages=find_packages(),
    install_requires=[
        "aiohttp",
        "beautifulsoup4",
        "lxml",
        "rich",
        "fake-useragent",
    ],
    entry_points={
        "console_scripts": [
            "contactharvest=contactharvest.cli:cli",
        ],
    },
    python_requires=">=3.7",
)
