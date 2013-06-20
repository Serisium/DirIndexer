#!/usr/bin/env python

from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh.fields import *
from whoosh import highlight
import os
import argparse
import codecs
import multiprocessing

def get_ix():
	schema = Schema(title=TEXT(stored=True), path=ID(stored=True,unique=True), content=TEXT, date=STORED)
	#create if not exists
	if not os.path.exists(".indexdir"):
		os.mkdir(".indexdir")
		create_in(".indexdir", schema)

	ix = open_dir(".indexdir")
	return ix

def get_cores(args):
	cores = multiprocessing.cpu_count()/2
	if args.processors:
		cores = args.processors

	return cores

def scan_directory(dir_nm, writer, all, exclude, checknew=False, to_index=set(), indexed_paths=set()):
	x = 0
	for root, sub_folders, files in os.walk(dir_nm, followlinks=True):
		#Remove hidden files
		if not all:
			files = [f for f in files if not f[0] == '.']
			sub_folders[:] = [d for d in sub_folders if not d[0] == '.'] #os.walk will not process deleted directories

		#Remove excluded files
		if exclude:
			files = [f for f in files if not os.path.splitext(f)[1][1:] in exclude]

		for cur_file in files:
			path = unicode(os.path.join(root, cur_file))

			#If a file is in the queue or is new, add it
			if checknew and path in to_index or path not in indexed_paths:
				add_doc(writer, path)
				x += 1
			elif not checknew:
				add_doc(writer, path)
				x += 1
	return x

def index(args):
	try:
		ix = get_ix()

		#get the number of cores to use
		procs = get_cores(args)

		writer = ix.writer(procs=procs)
		dir_nm = unicode(args.directory)

		#recursively scan the directory and add files
		x = 0
		x = scan_directory(dir_nm, writer, args.all, args.exclude)

	finally:
		print "Writing %d files to index" % x
		writer.commit()
		ix.close()


def update(args):
	try:
		ix = get_ix()

		#get the number of cores to use
		procs = get_cores(args)

		writer = ix.writer(procs=procs)
		indexed_paths = set()	#Holds all paths already indexed
		to_index = set()	#Holds a list of paths to index later

		x = 0
		with ix.searcher() as searcher:
			for fields in searcher.all_stored_fields():
				indexed_path = fields['path']
				indexed_paths.add(indexed_path)

				#if the file has been deleted, remove it from the index
				if not os.path.exists(indexed_path):
					writer.delete_by_term('path',indexed_path)
				else:
					indexed_time = fields['date']
					mtime = os.path.getmtime(indexed_path)

					#If file has been changed, delete it and add it to the queue
					if mtime > indexed_time:
						writer.delete_by_term('path',indexed_path)
						to_index.add(indexed_path)

			x = scan_directory(args.directory, writer, args.all, args.exclude, True, to_index, indexed_paths)

	finally:
		print "Writing " + str(x) + " files to index."
		writer.commit()
		ix.close()

def add_doc(writer, path):
	cur_file = codecs.open(path, encoding = 'utf-8', errors='ignore')
	content = cur_file.read()
	file_name = unicode(cur_file.name)
	path = unicode(path)
	modtime = os.path.getmtime(path)
	print "Indexing %s" % file_name
	writer.add_document(title=file_name, path=path, content=content, date=modtime)

def search(args):
	try:
		ix = get_ix()
		search_term = unicode(args.keyword)

		from whoosh.qparser import QueryParser
		with ix.searcher() as searcher:
			query = QueryParser("content", ix.schema).parse(u"%s" % search_term)
			results = searcher.search(query, terms=True, limit=args.limit)
			results.fragmenter = highlight.ContextFragmenter(maxchars=200, surround=20)

			#If stdin == stdout, the programs output is not being piped and colored output is fine
			color  = (args.color == 'always' or (args.color == 'auto' and os.fstat(0) == os.fstat(1)))
			results.formatter = ColorFormatter(color=color)

			print results
			for i, result in enumerate(results):
				if color:
					print "Results %i: \033[1;32m%s\033[1;m" % (i, result["path"])
				else:
					print "Results %i: %s" % (i, result["path"])
				with codecs.open(result["path"], encoding='utf-8', errors='ignore') as f:
					file_content = f.read()
					print result.highlights("content", text=file_content, top=10)
					print "\n"
	finally:
		ix.close()


def clear(args):
	print "Deleting the current index..."
	for root, dirs, files in os.walk(os.getcwd()+"/.indexdir/", topdown=False):
		for name in files:
			print name
			os.remove(os.path.join(root,name))
		for name in dirs:
			os.rmdir(os.path.join(root,name))
	os.rmdir(os.getcwd()+"/.indexdir/")

class ColorFormatter(highlight.Formatter):
	#Formatter for seach output

	def __init__(self, between="\n", color=True):
		self.between = between
		self.color = color
	def format_token(self, text, token, replace=False):
		tokentext = highlight.get_text(text, token, False)
		if self.color:
			return "\033[1;43m%s\033[1;m" % tokentext
		else:
			return tokentext

def start():
	parser = argparse.ArgumentParser(description='index a directory or search for keywords.')
	subparsers = parser.add_subparsers()

	parser_index = subparsers.add_parser('index', help="Index a given directory for future searches")
	parser_index.add_argument('directory', help="the directory to search")
	parser_index.set_defaults(func=index)
	parser_index.add_argument("-x", "--exclude", nargs='+', help="Exclude specified filetypes from index")
	parser_index.add_argument("-p", "--processors", type=int, help="Number of processors to utilize")
	parser_index.add_argument("-a", "--all", action='store_true', help="Include hidden files and folders in index")

	parser_update = subparsers.add_parser('update',help="Update the index with new or edited files")
	parser_update.add_argument('directory', help="The directory to update")
	parser_update.set_defaults(func=update)
	parser_update.add_argument("-x", "--exclude", nargs='+', help="Exclude specified filetypes from update")
	parser_update.add_argument("-p", "--processors", type=int, help="Number of processors to utilize")
	parser_update.add_argument("-a", "--all", action='store_true', help="Include hidden files and folders in update")

	parser_search = subparsers.add_parser('search', help="Search the indexed directory for a keyword")
	parser_search.add_argument('keyword', help="the search term")
	parser_search.set_defaults(func=search)
	parser_search.add_argument('-c', '--color', choices=['auto','always','never'], default='auto', type=str, help="Highlight the search term")
	parser_search.add_argument('-l', '--limit', type=int, default=None, help='Number of results to show; passing None will show all')

	parser_clear = subparsers.add_parser("clear", help="Delete the current index.")
	parser_clear.set_defaults(func=clear)

	args = parser.parse_args()
	args.func(args)

if __name__ == '__main__':
    start()
