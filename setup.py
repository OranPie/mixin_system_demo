from setuptools import setup, Extension
import os

accel_ext = Extension(
    'mixpy._accel',
    sources=['src/mixpy/_accel.c'],
)

# Only build C extension if explicitly requested
if os.environ.get('MIXPY_BUILD_ACCEL', '0') == '1':
    ext_modules = [accel_ext]
else:
    ext_modules = []

setup(
    ext_modules=ext_modules,
)
