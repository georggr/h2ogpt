"""Load Data from a MediaWiki dump xml."""
from typing import List, Optional
import os
import bz2
from langchain.docstore.document import Document
from langchain.document_loaders import MWDumpLoader
import csv

from tqdm import tqdm


class MWDumpDirectLoader(MWDumpLoader):
    def __init__(self, data: str, encoding: Optional[str] = "utf8"):
        """Initialize with file path."""
        self.data = data
        self.encoding = encoding

    def load(self) -> List[Document]:
        """Load from file path."""
        import mwparserfromhell
        import mwxml

        dump = mwxml.Dump.from_page_xml(self.data)

        docs = []

        for page in dump.pages:
            for revision in page:
                code = mwparserfromhell.parse(revision.text)
                text = code.strip_code(
                    normalize=True, collapse=True, keep_template_params=False
                )
                metadata = {"title": page.title, "source": "https://en.wikipedia.org/wiki/" + page.title}
                docs.append(Document(page_content=text, metadata=metadata))

        return docs


def search_index(search_term, index_filename):
    byte_flag = False
    data_length = start_byte = 0
    index_file = open(index_filename, 'r')
    csv_reader = csv.reader(index_file, delimiter=':')
    for line in csv_reader:
        if not byte_flag and search_term == line[2]:
            start_byte = int(line[0])
            byte_flag = True
        elif byte_flag and int(line[0]) != start_byte:
            data_length = int(line[0]) - start_byte
            break
    index_file.close()
    return start_byte, data_length


def get_start_bytes(index_filename):
    index_file = open(index_filename, 'r')
    csv_reader = csv.reader(index_file, delimiter=':')
    start_bytes = set()
    for line in csv_reader:
        start_bytes.add(int(line[0]))
    index_file.close()
    return sorted(start_bytes)


def get_wiki_filenames():
    base_path = '/data/jon/enwiki-20230401-pages-articles-multistream'
    index_file = 'enwiki-20230401-pages-articles-multistream-index.txt'
    index_filename = os.path.join(base_path, index_file)
    wiki_filename = os.path.join(base_path, 'enwiki-20230401-pages-articles-multistream.xml.bz2')
    return index_filename, wiki_filename


def get_documents_by_search_term(search_term):
    index_filename, wiki_filename = get_wiki_filenames()
    start_byte, data_length = search_index(search_term, index_filename)
    with open(wiki_filename, 'rb') as wiki_file:
        wiki_file.seek(start_byte)
        data = bz2.BZ2Decompressor().decompress(wiki_file.read(data_length))

    loader = MWDumpDirectLoader(data.decode())
    documents = loader.load()
    return documents


from joblib import parallel_backend


def get_one_chunk(wiki_filename, start_byte, end_byte):
    data_length = end_byte - start_byte
    with open(wiki_filename, 'rb') as wiki_file:
        wiki_file.seek(start_byte)
        data = bz2.BZ2Decompressor().decompress(wiki_file.read(data_length))

    loader = MWDumpDirectLoader(data.decode())
    documents1 = loader.load()
    return documents1


from joblib import Parallel, delayed


def get_all_documents(small_test=False):
    print("DO get all wiki docs", flush=True)
    index_filename, wiki_filename = get_wiki_filenames()
    start_bytes = get_start_bytes(index_filename)
    end_bytes = start_bytes[1:]
    start_bytes = start_bytes[:-1]

    if small_test:
        start_bytes = start_bytes[:2]
        end_bytes = end_bytes[:2]
        n_jobs = 1
    else:
        n_jobs = os.cpu_count() // 4

    documents = Parallel(n_jobs=n_jobs, verbose=10)(
        delayed(get_one_chunk)(wiki_filename, start_byte, end_byte) for start_byte, end_byte in
        zip(start_bytes, end_bytes))

    from functools import reduce
    from operator import concat
    documents = reduce(concat, documents)
    assert isinstance(documents, list)

    print("DONE get all wiki docs", flush=True)
    return documents


def test_by_search_term():
    search_term = 'Apollo'
    assert len(get_documents_by_search_term(search_term)) == 100

    search_term = 'Abstract (law)'
    assert len(get_documents_by_search_term(search_term)) == 100

    search_term = 'Artificial languages'
    assert len(get_documents_by_search_term(search_term)) == 100


def test_start_bytes():
    index_filename, wiki_filename = get_wiki_filenames()
    assert len(get_start_bytes(index_filename)) == 227850


def test_get_all_documents():
    assert len(get_all_documents()) == 100 * 227850
