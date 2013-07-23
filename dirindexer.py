#usr/bin/env python

from whoosh.index import create_in
from whoosh.index import open_dir
from whoosh.fields import Schema, TEXT, ID, STORED
from whoosh.analysis import SpaceSeparatedTokenizer, LowercaseFilter
from whoosh.writing import BufferedWriter
from whoosh import highlight
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import watchdog.utils
import os
import argparse
import codecs
import multiprocessing
import threading
import colorama
import time
import Queue


class DirIndexer:
    """
    Pure Python command line utility for efficiently indexing then searching
    a directory
    """
    def __init__(self, args):
        """
        Initialization function

        Parameters
        ----------
        args:   The namespace created by argparse containing several options
                for each of dirindexer's modes

            index, update, daemon:
                directory : str
                    The directory to process.
                exclude : list of str, optional
                    List of filetypes to exclude from the process.
                include : list of str, optional
                    List of filetypes to only include in the process.
                processors : int, optional
                    Number of processor cores to use in the process,
                    defaults to 1/2 of cores available
                all : bool, default=false, optional
                    Whether to include hidden files and directories in
                    the process

            daemon(continued):
                delay : float
                    Amount of time to wait in between each index commit.

            search:
                keyword : str
                    The keyword to search for
                color : {'always', 'auto'}, optional
                    Whether or not to colorize search results. Defaults
                    to auto unless 'always' or something else is set.
                    In auto mode, text will always be highlighted
                    unless output is being piped
                limit : int, optional
                    The number of terms to display. Default is 0, or
                    no limit
                exclude : list of str, optional
                    List of filetypes to exclude from the search
                include : list of str, optional
                    List of filetypes to only include in search
        """
        if(args.func == DirIndexer.index
           or args.func == DirIndexer.update
           or args.func == DirIndexer.daemon
           ):
            self.directory = args.directory
            self.exclude = args.exclude
            self.include = args.include
            self.processors = args.processors
            self.all = args.all

        if args.func == DirIndexer.daemon:
            if args.delay is not None:
                self.delay = args.delay
            else:
                self.delay = 5.0
        if args.func == DirIndexer.search:
            self.keyword = args.keyword
            self.color = args.color
            self.limit = args.limit
            self.exclude = args.exclude
            self.include = args.include

        if args.func == DirIndexer.clear:
            pass

    def get_ix(self):
        """Creates the Schema and returns the index_writer"""
        schema = Schema(title=TEXT(stored=True),
                        path=ID(stored=True, unique=True),
                        content=TEXT(analyzer=
                                     SpaceSeparatedTokenizer() |
                                     LowercaseFilter()),
                        date=STORED)
        #create if not exists
        if not os.path.exists(".indexdir"):
            os.mkdir(".indexdir")
            create_in(".indexdir", schema)

        ix = open_dir(".indexdir")
        return ix

    def get_cores(self):
        """Returns the appropriate number of processor cores to use"""
        cores = multiprocessing.cpu_count() / 2

        if self.processors:
            cores = self.processors

        return cores

    def scan_directory(self, dir_nm, writer, checknew=False,
                       to_index=set(), indexed_paths=set()):
        """
        Scans a directory, adds files to be processed to the index
        writer, then returns the number of changes
        Does not commit changes

        Parameters
        ----------
        dir_nm : str
            The directory to scan
        writer : whoosh.writing.IndexWriter
            The whoosh index writer object to use
        checknew : bool, optional
           Whether to only add new files or files from new folders
           to the index
        to_index : set, str, optional
            For use with checknew
            A list of new directories to index
        indexed_paths : set, str, optional
            For use with checknew
            A list of directories that have already been searched

        Returns
        -------
        x : int
            Number of files that have been added to the index
        """
        x = 0
        print dir_nm
        for root, sub_folders, files in os.walk(dir_nm, followlinks=True):
            #Remove hidden files
            if not self.all:
                files = [f for f in files if not f[0] == '.']
                #os.walk will not process deleted directories
                sub_folders[:] = [d for d in sub_folders if not d[0] == '.']

            #Remove excluded files
            if self.exclude:
                files = [f for f in files
                         if not os.path.splitext(f)[1][1:]
                         in self.exclude]
            if self.include:
                files = [f for f in files
                         if os.path.splitext(f)[1][1:]
                         in self.include]

            for cur_file in files:
                path = unicode(os.path.join(root, cur_file))

                #If a file is in the queue or is new, add it
                if checknew and path in to_index or path not in indexed_paths:
                    self.add_doc(writer, path)
                    x += 1
                elif not checknew:
                    self.add_doc(writer, path)
                    x += 1
        return x

    def index(self):
        """
        Index function
        Adds self.directory to the index.
        """
        ix = self.get_ix()

        #get the number of cores to use
        procs = self.get_cores()

        writer = ix.writer(procs=procs)
        dir_nm = unicode(self.directory)

        #recursively scan the directory and add files
        x = self.scan_directory(dir_nm, writer)

        print "Writing %d files to index" % x
        writer.commit()
        ix.close()

    def update(self):
        """
        Update function
        Checks self.directory for changes and adds them to the index
        """

        try:
            ix = self.get_ix()

            #get the number of cores to use
            procs = self.get_cores()

            writer = ix.writer(procs=procs)
            indexed_paths = set()   # Holds all paths already indexed
            to_index = set()    # Holds a list of paths to index later

            x = 0
            with ix.searcher() as searcher:
                for fields in searcher.all_stored_fields():
                    indexed_path = fields['path']
                    indexed_paths.add(indexed_path)

                    #if the file has been deleted, remove it from the index
                    if not os.path.exists(indexed_path):
                        self.remove_doc(writer, indexed_path)
                    else:
                        indexed_time = fields['date']
                        mtime = os.path.getmtime(indexed_path)

                        #If file has been changed,
                        #delete it and add it to the queue
                        if mtime > indexed_time:
                            self.remove_doc(writer, indexed_path)
                            to_index.add(indexed_path)

                x = self.scan_directory(self.directory, writer,
                                        True, to_index, indexed_paths)

        finally:
            print "Writing " + str(x) + " files to index."
            writer.commit()
            ix.close()

    def daemon(self):
        """
        Daemon function
        Continuosly watches self.directory for
        changes and adds them to the index.
        """
        ix = self.get_ix()
        writer = BufferedWriter(ix, limit=100)
        event_handler = IndexWriterEventHandler(writer, self, self.all,
                                                self.exclude, self.include,
                                                )
        observer = Observer()
        observer.schedule(event_handler, path=self.directory, recursive=True)
        observer.start()
        #observer.should_keep_running()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
            writer.commit()
            ix.close()
        observer.join()

    def add_doc(self, writer, path):
        """Writes a given file to the index_writer"""

        cur_file = codecs.open(path, encoding='utf-8', errors='ignore')
        content = cur_file.read()
        file_name = unicode(cur_file.name)
        path = unicode(path)
        modtime = os.path.getmtime(path)
        print "Indexing %s" % file_name
        writer.add_document(title=file_name, path=path,
                            content=content, date=modtime)

    def remove_doc(self, writer, path):
        """Removes a given file from index_writer"""

        print "Removing %s" % path
        writer.delete_by_term('path', path)

    def search(self):
        """
        Search function
        Searches all indexes for self.keyword and prints them.
        """

        try:
            ix = self.get_ix()
            search_term = unicode(self.keyword)

            from whoosh.qparser import QueryParser
            with ix.searcher() as searcher:
                query = QueryParser("content", ix.schema).parse(
                    u"%s" % search_term)
                results = searcher.search(query, terms=True, limit=self.limit)
                results.fragmenter = highlight.ContextFragmenter(maxchars=200,
                                                                 surround=20)

                #If stdin == stdout, the programs output is not being
                #piped and colored output is fine
                color = (self.color == 'always'
                         or (self.color == 'auto'
                             and os.fstat(0) == os.fstat(1)))
                results.formatter = ColorFormatter(color=color)

                #Remove excluded filetypes from search results
                if self.exclude:
                    results = [f for f in results
                               if not os.path.splitext(f["path"])[1][1:]
                               in self.exclude]
                if self.include:
                    results = [f for f in results
                               if os.path.splitext(f["path"])[1][1:]
                               in self.include]

                print results
                for i, result in enumerate(results, start=1):
                    if color:
                        print "Result %i: %s" % (
                            i, colorama.Fore.GREEN + result["path"]
                            + colorama.Fore.RESET)
                    else:
                        print "Result %i: %s" % (i, result["path"])
                    with codecs.open(result["path"],
                                     encoding='utf-8',
                                     errors='ignore') as f:
                        file_content = f.read()
                        print result.highlights("content",
                                                text=file_content,
                                                top=10)
                        print "\n"
        finally:
            ix.close()

    def clear(self):
        """Deletes all indexes"""

        print "Deleting the current index..."
        for root, dirs, files in os.walk(os.getcwd() + "/.indexdir/",
                                         topdown=False):
            for name in files:
                print name
                os.remove(os.path.join(root, name))
            for name in dirs:
                os.rmdir(os.path.join(root, name))
        os.rmdir(os.getcwd() + "/.indexdir/")


class ColorFormatter(highlight.Formatter):
    """Class that handles colorized search output"""

    def __init__(self, between="\n", color=True):
        self.between = between
        self.color = color

    def format_token(self, text, token, replace=False):
        tokentext = highlight.get_text(text, token, False)
        if self.color:
            return colorama.Back.YELLOW + tokentext + colorama.Back.RESET
        else:
            return tokentext


class IndexWriterEventHandler(FileSystemEventHandler):
    """
    Event handler customized for updating a directory with file changes.
    Implements a LIFO queue to eliminate redundant commits.
    """
    def __init__(self, writer, di, all=False,
                 exclude=[], include=None, delay=5.0):
        self.writer = writer
        self.di = di
        self.all = all
        self.exclude = exclude
        self.include = include
        self.delay = delay
        self.queue = Queue.LifoQueue()
        self.clear_queue()

    def dispatch(self, event):
        print("Adding event to queue...")
        self.on_any_event(event)
        self.queue.put(event)

    def clear_queue(self):
        """Commits queue to index and clears it."""
        print("Emtpying queue...")
        urls = []
        while not self.queue.empty():
            event = self.queue.get()
            if watchdog.utils.has_attribute(event, 'dest_path'):
                if event.dest_path not in urls:
                    urls.append(event.dest_path)
                    FileSystemEventHandler.dispatch(self, event)
            else:
                if event.src_path not in urls:
                    urls.append(event.src_path)
                    FileSystemEventHandler.dispatch(self, event)

        if urls != []:
            print("Commiting %i changes." % len(urls))
            self.writer.commit()
            print("Done.")

        threading.Timer(self.delay, self.clear_queue).start()

    def pathIsGood(self, path):
        """
        Analyzes path according to rules in self.all, self.include,
        and self.exclude and returns whether the path passes.
        """
        if not self.all:
            if os.path.basename(path)[0] == '.':
                return False
        if self.exclude:
            if os.path.splitext(path)[1][1:] in self.exclude:
                return False
        if self.include:
            if os.path.splitext(path)[1][1:] not in self.include:
                return False
        return True

    def on_created(self, event):
        #print("on_create")
        if self.pathIsGood(event.src_path):
            self.di.add_doc(self.writer, event.src_path)

    def on_moved(self, event):
        #print("on_moved")
        self.di.remove_doc(self.writer, event.src_path)
        if self.pathIsGood(event.dest_path):
            self.di.add_doc(self.writer, event.dest_path)

    def on_deleted(self, event):
        #print("on_deleted")
        self.di.remove_doc(self.writer, event.src_path)

    def on_modified(self, event):
        #print("on_modified")
        if self.pathIsGood(event.src_path):
            self.di.remove_doc(self.writer, event.src_path)
            self.di.add_doc(self.writer, event.src_path)


def start():

    colorama.init()

    parser = argparse.ArgumentParser(
        description='index a directory or search for keywords.')
    subparsers = parser.add_subparsers()

    parser_index = subparsers.add_parser(
        'index', help="Index a given directory for future searches")
    parser_index.add_argument('directory', help="the directory to search")
    parser_index.set_defaults(func=DirIndexer.index)
    parser_index_filegroup = parser_index.add_mutually_exclusive_group()
    parser_index_filegroup.add_argument(
        "-x", "--exclude", nargs='+',
        help="Exclude specified filetypes from index")
    parser_index_filegroup.add_argument(
        "-i", "--include", nargs='+',
        help="Include only the specified filetypes in the index")
    parser_index.add_argument("-p", "--processors", type=int,
                              help="Number of processors to utilize")
    parser_index.add_argument("-a", "--all", action='store_true',
                              help="Include hidden files and folders in index")

    parser_update = subparsers.add_parser(
        'update', help="Update the index with new or edited files")
    parser_update.add_argument('directory', help="The directory to update")
    parser_update.set_defaults(func=DirIndexer.update)
    parser_update_filegroup = parser_update.add_mutually_exclusive_group()
    parser_update_filegroup.add_argument(
        "-x", "--exclude", nargs='+',
        help="Exclude specified filetypes from update")
    parser_update_filegroup.add_argument(
        "-i", "--include", nargs='+',
        help="Include only the specified filetypes in the update")
    parser_update.add_argument(
        "-p", "--processors", type=int, help="Number of processors to utilize")
    parser_update.add_argument(
        "-a", "--all", action='store_true',
        help="Include hidden files and folders in update")

    parser_daemon = subparsers.add_parser(
        'daemon', help="Start a daemon to automatically update the index.")
    parser_daemon.add_argument('directory', help="The directory to watch.")
    parser_daemon.set_defaults(func=DirIndexer.daemon)
    parser_daemon_filegroup = parser_daemon.add_mutually_exclusive_group()
    parser_daemon_filegroup.add_argument(
        "-x", "--exclude", nargs='+',
        help="Exclude the specified filetypes from the updates.")
    parser_daemon_filegroup.add_argument(
        "-i", "--include", nargs='+',
        help="Include only the specified filetypes in the updates.")
    parser_daemon.add_argument(
        "-p", "--processors", type=int, help="Number of processors to utilize")
    parser_daemon.add_argument(
        "-a", "--all", action='store_true',
        help="Include hidden files and directories in the update.")
    parser_daemon.add_argument(
        "-d", "--delay", type=float,
        help="Delay in between commits")

    parser_search = subparsers.add_parser(
        'search', help="Search the indexed directory for a keyword")
    parser_search.add_argument('keyword', help="the search term")
    parser_search.set_defaults(func=DirIndexer.search)
    parser_search.add_argument(
        '-c', '--color', choices=['auto', 'always', 'never'],
        default='auto', type=str,
        help="Highlight the search term")
    parser_search.add_argument(
        '-l', '--limit', type=int,
        default=None,
        help='Number of results to show; passing None will show all')
    parser_search_filegroup = parser_search.add_mutually_exclusive_group()
    parser_search_filegroup.add_argument(
        '-x', "--exclude", nargs='+',
        help="Exclude specified filetypes from search")
    parser_search_filegroup.add_argument(
        '-i', "--include", nargs='+',
        help="Include only the specified filetypes in the search")

    parser_clear = subparsers.add_parser(
        "clear", help="Delete the current index.")
    parser_clear.set_defaults(func=DirIndexer.clear)

    args = parser.parse_args()

    di = DirIndexer(args)

    args.func(di)

if __name__ == '__main__':
    start()
