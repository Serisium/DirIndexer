from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh.fields import *
import os

def get_ix():
	schema = Schema(title=TEXT(stored=True), path=ID(stored=True), content=TEXT)
	#create if not exists
	if not os.path.exists(".indexdir"):
		os.mkdir(".indexdir")
		create_in(".indexdir", schema)

	ix = open_dir(".indexdir")
	return ix

def index(ix, dir_nm):
	writer = ix.writer()
	for root, sub_folders, files in os.walk(dir_nm):
		for cur_file in files:
			cur_file = open(cur_file)
			print "indexing %s" % cur_file.name
			#items to index
			content = u"%s" % cur_file.read()
			file_name = u"%s" % cur_file.name
			path = u"%s" % os.path.join(root, cur_file.name)
			writer.add_document(title=file_name, path=path, content=content)
	writer.commit()


def search(ix, search_term):
	from whoosh.qparser import QueryParser
	with ix.searcher() as searcher:
		query = QueryParser("content", ix.schema).parse(u"%s" % search_term)
		results = searcher.search(query, terms=True)
		print results
		results.fragmenter.charlimit = 10000000
		for result in results:
			print "result **"
			with open(result["path"]) as f:
				file_content = u"%s" % f.read()
			print result.highlights("content", text=file_content, top=10)

if __name__ == '__main__':
	try:
		ix = get_ix()

		dir_nm = "/home/david/Developer/repos/dirindexer/files"
		index(ix, dir_nm)

		search(ix, "david")
	finally:
		ix.close()
