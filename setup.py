#!/usr/bin/env python

from setuptools import setup, find_packages

setup(name='DirIndexer',
	version='1.1',
	description='Pure Python command line utility for efficiently indexing then searching a directory',
	author='Garrett Greenwood, David Sounthiraraj',
	author_email='garrettagreenwood@gmail.com',
	url='https://github.com/GGreenwood/DirIndexer',
    package_dir = {'': 'src'},
    packages = find_packages('src'),
    scripts=['src/dirindexer.py'],
	entry_points= {
		'console_scripts': [
			'dirindexer = dirindexer:start'
		]
	},
	install_requires=[
		'Whoosh>=2.4.1',
		'colorama>=0.2.5',
		'watchdog>=0.6.0'
	]
)
