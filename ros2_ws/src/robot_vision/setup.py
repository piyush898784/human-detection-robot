from setuptools import setup
import os
from glob import glob

package_name = 'robot_vision'

setup(
    name=package_name,
    version='1.0.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages',
            ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='Priyam Patel',
    maintainer_email='priyam@robotics.edu',
    description='Vision processing nodes for autonomous host detection, face recognition, and tracking using YOLOv11 and InsightFace.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'camera_node = robot_vision.camera_node:main',
            'person_detection_node = robot_vision.person_detection_node:main',
        ],
    },
)
