from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh import highlight
from whoosh.fields import *
import os
import argparse

def get_ix():
	schema = Schema(title=TEXT(stored=True), path=ID(stored=True), content=TEXT)
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
			for cur_file in files:
				fullpath =  root + "/" + cur_file
				cur_file = open(fullpath)
				print "indexing %s" % cur_file.name
				#items to index
				content = u"%s" % removeNonAscii(cur_file.read())
				file_name = u"%s" % cur_file.name
				path = u"%s" % os.path.join(root, cur_file.name)
				writer.add_document(title=file_name, path=path, content=content)
				#print title + '\t\t' + path + '\t\t' + content + '\n' 
		writer.commit()
	finally:
		ix.close()

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
			i=1
			for result in results:
				print "Result " + str(i) + ": " + result["path"]
				
				i+=1
				with open(result["path"]) as f:
					file_content = u"%s" % removeNonAscii(f.read())
				print result.highlights("content", text=file_content, top=10)
				print "\n"
	finally:
		ix.close()

def removeNonAscii(s):
	return "".join(i for i in s if ord(i)<128)

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description='index a directory or search for keywords.')
	subparsers = parser.add_subparsers()

	parser_index = subparsers.add_parser('index', help="index a given directory for future searches")
	parser_index.add_argument('directory', help="the directory to search")
	parser_index.set_defaults(func=index)
	
	parser_search = subparsers.add_parser('search', help="search the indexed directory for a keyword")
	parser_search.add_argument('keyword', help="the search term")
	parser_search.set_defaults(func=search)
	
	args=parser.parse_args()
	args.func(args)

