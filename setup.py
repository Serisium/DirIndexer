#!/usr/bin/env python

from setuptools import setup

setup(name='DirIndexer',
	version='1.0',
	scripts=['dirindexer.py'],
	entry_points= {
		'console_scripts': [
			'dirindexer = dirindexer:start'
		]
	},
	install_requires='Whoosh>=2.4.1'
)
