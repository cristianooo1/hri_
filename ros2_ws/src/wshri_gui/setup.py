from glob import glob
import os
import sys
from setuptools import setup

package_name = "wshri_gui"

def package_files(directory):
    paths = []
    for (path, directories, filenames) in os.walk(directory):
        for filename in filenames:
            paths.append(os.path.join(path, filename))
    return paths

extra_files = []
web_root = 'web'
for root, dirs, files in os.walk(web_root):
    for file in files:
        
        install_path = os.path.join('share', package_name, root)
        file_path = os.path.join(root, file)
        extra_files.append((install_path, [file_path]))

unsupported_flags = {"--editable", "--build-directory"}
cleaned_args = []
skip_next = False
for idx, arg in enumerate(sys.argv):
    if skip_next:
        skip_next = False
        continue
    if arg in unsupported_flags:
        if idx + 1 < len(sys.argv) and not sys.argv[idx + 1].startswith("-"):
            skip_next = True
        continue
    cleaned_args.append(arg)
sys.argv = cleaned_args

setup(
    name=package_name,
    version="0.0.1",
    packages=[package_name],
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        *extra_files,
    ],
    install_requires=[
        "setuptools",
        "google-genai",
        "python-dotenv",
        "pygame",           # for llm.py
        "edge-tts",         #  for llm.py
        "faster-whisper",   #  for llm.py
        "SpeechRecognition", # for llm.py
    ],
    zip_safe=True,
    maintainer="WSHRI Team",
    maintainer_email="team@example.com",
    description="Web-based GUI for the WSHRI robot visualization.",
    license="MIT",
    entry_points={
        "console_scripts": [
            "gui_server = wshri_gui.gui_server:main",
        ],
    },
)
