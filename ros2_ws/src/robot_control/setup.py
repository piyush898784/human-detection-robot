from setuptools import setup

package_name = 'robot_control'

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
    description='Control planning nodes and PID speed profile generator communicating with the LILYGO motor drivers.',
    license='MIT',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'motion_planner_node = robot_control.motion_planner_node:main',
        ],
    },
)
