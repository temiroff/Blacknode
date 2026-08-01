from setuptools import find_packages, setup


package_name = "lesson_04_package"


setup(
    name=package_name,
    version="0.0.1",
    packages=find_packages(),
    data_files=[
        ("share/ament_index/resource_index/packages", [f"resource/{package_name}"]),
        (f"share/{package_name}", ["package.xml"]),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Blacknode Tutorial",
    maintainer_email="tutorial@example.com",
    description="Blacknode ROS 2 tutorial package for lesson 04.",
    license="Apache-2.0",
    entry_points={
        "console_scripts": [
            "publisher = lesson_04_package.publisher:main",
        ],
    },
)
