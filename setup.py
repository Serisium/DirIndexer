#!/usr/bin/env python

from setuptools import setup

setup(name='DirIndexer',
	version='1.1',
	description='Pure Python command line utility for efficiently indexing then searching a directory',
	author='Garrett Greenwood, David Sounthiraraj',
	author_email='garrettagreenwood@gmail.com',
	url='https://bitbucket.org/sdbrain/dirindexer/overview',
	scripts=['dirindexer.py'],
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
