from glob import glob
import os

from setuptools import setup

package_name = "wshri_gui"

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name],
        ),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "web"), glob("web/*")),
    ],
    install_requires=[
        "setuptools",
        "google-genai",
        "python-dotenv",
    ],
    zip_safe=True,
    maintainer="WSHRI Team",
    maintainer_email="team@example.com",
    description="Web-based GUI for the WSHRI robot visualization.",
    license="MIT",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "gui_server = wshri_gui.gui_server:main",
        ],
    },
)
