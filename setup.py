import io
import os

from setuptools import find_packages, setup

__version__ = "0.1.1"


def read_from(file):
    reply = []
    with io.open(os.path.join(here, file), encoding='utf8') as f:
        for l in f:
            l = l.strip()
            if not l:
                break
            if l[:2] == '-r':
                reply += read_from(l.split(' ')[1])
                continue
            if l[0] != '#' or l[:2] != '//':
                reply.append(l)
    return reply


here = os.path.abspath(os.path.dirname(__file__))
with io.open(os.path.join(here, 'README.rst'), encoding='utf8') as f:
    README = f.read()

setup(
    name="push-test",
    version=__version__,
    packages=find_packages(),
    description='Autopush Smoke Test',
    long_description=README,
    classifiers=[
        "Topic :: Internet :: WWW/HTTP",
        'Programming Language :: Python',
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
    ],
    keywords="autopush test",
    author="JR Conlin",
    author_email="jr+src@mozilla.com",
    license="MPL2",
    test_suite="pytest.collector",
    include_package_data=True,
    zip_safe=False,
    install_requires=read_from('requirements.txt'),
    setup_requires=['pytest-runner'],
    test_requires=read_from('test-requirements.txt'),
    entry_points="""
    [console_scripts]
    push-test = push_test.__main__:main
    """,
)
