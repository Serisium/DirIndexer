'''
Created on May 28, 2013

@author: david
'''
from whoosh import fields
from whoosh.index import create_in
from datetime import datetime
import os
from whoosh.qparser import QueryParser


class DirSchema(fields.SchemaClass):
    file_name = fields.ID(stored=True)
    content = fields.TEXT
    path = fields.ID(stored=True)
    indexed_on = fields.DATETIME(stored=True)


def index(dir_nm):
	schema = DirSchema()
	if not os.path.exists(".indexdir"):
		os.mkdir(".indexdir")

	ix = create_in(".indexdir", schema)
	w = ix.writer()
	for root, sub_folder, files in os.walk(dir_nm):
		for cur_file in files:
			cur_file = open(cur_file)
			print "indexing %s" % cur_file.name

			#items to index
			content = u"%s" % cur_file.read()
			file_name = u"%s" % cur_file.name
			path = u"%s" % os.path.join(
                           root, cur_file.name)

			w.add_document(file_name=file_name,
                           content=content,
                           path=path,
                           indexed_on=datetime.now())
	w.commit()

def search(term):
	schema = DirSchema()
	ix = create_in(".indexdir", schema)
	with ix.searcher() as searcher:
		query = QueryParser("content", ix.schema).parse(term)
		results = searcher.search(query)
		print results
		for result in results:
			print result

if __name__ == '__main__':
    dir_nm = "/home/david/Developer/repos/dirindexer/files"
    index(dir_nm)
    term = u"schema"
    search(term)
