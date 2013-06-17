from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh import highlight
from whoosh.fields import *
import os
import argparse

def get_ix():
	schema = Schema(title=TEXT(stored=True), path=ID(stored=True,unique=True), content=TEXT, date=STORED)
	#create if not exists
	if not os.path.exists(".indexdir"):
		os.mkdir(".indexdir")
		create_in(".indexdir", schema)

	ix = open_dir(".indexdir")
	return ix

def index(args):
	try:
		ix = get_ix()
		writer = ix.writer()
		dir_nm = removeNonAscii(args.directory)
		for root, sub_folders, files in os.walk(dir_nm):
			files = [f for f in files if not f[0] == '.']
			sub_folders[:] = [d for d in sub_folders if not d[0] == '.'] #os.walk will not process deleted directories

			if args.exclude is not None:
				files = [f for f in files if not os.path.splitext(f)[1][1:] in args.exclude]
			
			for cur_file in files:
				fullpath = u"%s" % os.path.join(root, cur_file)
				add_doc(writer, fullpath)
	finally:
		writer.commit()
		ix.close()

def update(args):
	try:
		ix = get_ix()
		writer = ix.writer()
		indexed_paths = set()
		to_index = set()

		with ix.searcher() as searcher:
			for fields in searcher.all_stored_fields():
				indexed_path = fields['path']
				indexed_paths.add(indexed_path)
				
				if not os.path.exists(indexed_path):
					writer.delete_by_term('path',indexed_path)
				else:
					indexed_time = fields['date']
					mtime = os.path.getmtime(indexed_path)
					if mtime > indexed_time:
						writer.delete_by_term('path',indexed_path)
						to_index.add(indexed_path)
			
			for root, sub_folders, files in os.walk(args.directory):
				files = [f for f in files if not f[0] == '.']
				sub_folders[:] = [d for d in sub_folders if not d[0] == '.']
				
				if args.exclude is not None:
					files = [f for f in files if not os.path.splitext(f)[1][1:] in args.exclude]
				
				for cur_file in files:
					path = u"%s" % os.path.join(root,cur_file)
					if path in to_index or path not in indexed_paths:
						add_doc(writer, path)
	
	finally:
		writer.commit()
		ix.close()

def add_doc(writer, path):
	cur_file = open(path)
	content = u"%s" % removeNonAscii(cur_file.read())
	file_name = u"%s" % cur_file.name
	path = u"%s" % path
	modtime = os.path.getmtime(path)
	print "Indexing %s" % file_name 
	writer.add_document(title=file_name, path=path, content=content, date=modtime)

def search(args):
	try:
		ix = get_ix()
		search_term = removeNonAscii(args.keyword)
	
		from whoosh.qparser import QueryParser
		with ix.searcher() as searcher:
			query = QueryParser("content", ix.schema).parse(u"%s" % search_term)
			results = searcher.search(query, terms=True)
			print results
			results.fragmenter = highlight.ContextFragmenter(maxchars = 300, surround = 50, charlimit = 1000000)
			results.order = highlight.SCORE
			for i, result in enumerate(results):
				print "Result " + str(i) + ": " + result["path"]
				
				i+=1
				with open(result["path"]) as f:
					file_content = u"%s" % removeNonAscii(f.read())
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

def removeNonAscii(s):
	return "".join(i for i in s if ord(i)<128)

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='index a directory or search for keywords.')
	subparsers = parser.add_subparsers()
	
	parser_clear = subparsers.add_parser("clear", help="Delete the current index.")
	parser_clear.set_defaults(func=clear)

	parser_index = subparsers.add_parser('index', help="Index a given directory for future searches")
	parser_index.add_argument('directory', help="the directory to search")
	parser_index.set_defaults(func=index)
	parser_index.add_argument("-x", "--exclude", nargs='+', help="Exclude specified filetypes from index")

	parser_update = subparsers.add_parser('update',help="Update the index with new or edited files")
	parser_update.add_argument('directory', help="The directory to update")
	parser_update.set_defaults(func=update)
	parser_update.add_argument("-x", "--exclude", nargs='+', help="Exclude specified filetypes from update")

	parser_search = subparsers.add_parser('search', help="Search the indexed directory for a keyword")
	parser_search.add_argument('keyword', help="the search term")
	parser_search.set_defaults(func=search)
	
	args=parser.parse_args()
	args.func(args)

