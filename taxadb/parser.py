#!/usr/bin/env python
# -*- coding: utf-8 -*-

import gzip
import os
from taxadb.schema import Taxa, Accession
from taxadb.util import fatal


class TaxaParser(object):
    """Base parser class for taxonomic files"""

    def __init__(self, verbose=False):
        """
        Base class
        """
        self._verbose = verbose

    def check_file(self, element):
        """Make some check on a file

        This method is used to check an `element` is a real file.

        Args:
            element (:obj:`type`): File to check

        Returns:
            True

        Raises:
            SystemExit: if `element` file does not exist
            SystemExit: if `element` is not a file

        """
        if element is None:
            fatal("Please provide an input file to check")
        if not os.path.exists(element):
            fatal("File %s does not exist" % str(element))
        if not os.path.isfile(element):
            fatal("%s is not a file" % str(element))
        return True

    def verbose(self, msg):
        """Prints some message if verbose mode on"""
        if self._verbose is True and msg and msg != '':
            print("[VERBOSE] %s" % str(msg))
        return True


class TaxaDumpParser(TaxaParser):
    """Main parser class for ncbi taxdump files

    This class is used to parse NCBI taxonomy files found in taxdump.gz archive

    Args:
        nodes_file (:obj:`str`): Path to nodes.dmp file
        names_file (:obj:`str`): Path to names.dmp file

    """
    def __init__(self, nodes_file=None, names_file=None, **kwargs):
        """

        """
        super().__init__(**kwargs)
        self.nodes_file = nodes_file
        self.names_file = names_file

    def taxdump(self, nodes_file=None, names_file=None):
        """Parse .dmp files

        Parse nodes.dmp and names.dmp files (from taxdump.tgz) and insert
            taxons in Taxa table.

        Args:
            nodes_file (:obj:`str`): Path to nodes.dmp file
            names_file (:obj:`str`): Path to names.dmp file

        Returns:
            list: Zipped data from both files

        """
        if nodes_file is None:
            nodes_file = self.nodes_file
        if names_file is None:
            names_file = self.names_file
        self.check_file(names_file)
        self.check_file(nodes_file)
        # parse nodes.dmp
        nodes_data = list()
        self.verbose("Loading taxa data ...")
        ncbi_ids = {str(x['ncbi_taxid']): True for x in Taxa.select(
            Taxa.ncbi_taxid).dicts()}
        self.verbose("Parsing %s" % str(nodes_file))
        with open(nodes_file, 'r') as f:
            for line in f:
                line_list = line.split('|')
                ncbi_id = line_list[0].strip('\t')
                if ncbi_id in ncbi_ids:
                    continue
                data_dict = {
                    'ncbi_taxid': ncbi_id,
                    'parent_taxid': line_list[1].strip('\t'),
                    'tax_name': '',
                    'lineage_level': line_list[2].strip('\t')
                    }
                nodes_data.append(data_dict)
        print('parsed nodes')

        # parse names.dmp
        names_data = list()
        self.verbose("Parsing %s" % str(names_file))
        with open(names_file, 'r') as f:
            for line in f:
                if 'scientific name' in line:
                    line_list = line.split('|')
                    ncbi_id = line_list[0].strip('\t')
                    if ncbi_id in ncbi_ids:
                        continue
                    data_dict = {
                        'ncbi_taxid': line_list[0].strip('\t'),
                        'tax_name': line_list[1].strip('\t')
                    }
                    names_data.append(data_dict)
        print('parsed names')

        # merge the two dictionaries
        taxa_info_list = list()
        for nodes, names in zip(nodes_data, names_data):
            taxa_info = {**nodes, **names}  # PEP 448, requires python 3.5
            taxa_info_list.append(taxa_info)
        print('merge successful')
        return taxa_info_list

    def set_nodes_file(self, nodes_file):
        """Set nodes_file

        Set the accession file to use

        Args:
            nodes_file (:obj:`str`): Nodes file to be set

        Returns:
            True

        Raises:
            SystemExit: If `nodes_file` is None or not a file (`check_file`)

        """
        if nodes_file is None:
            fatal("Please provide an accession file to set")
        self.check_file(nodes_file)
        self.nodes_file = nodes_file
        return True

    def set_names_file(self, names_file):
        """Set names_file

        Set the accession file to use

        Args:
            names_file (:obj:`str`): Nodes file to be set

        Returns:
            True

        Raises:
            SystemExit: If `names_file` is None or not a file (`check_file`)

        """
        if names_file is None:
            fatal("Please provide an accession file to set")
        self.check_file(names_file)
        self.names_file = names_file
        return True


class Accession2TaxidParser(TaxaParser):
    """Main parser class for nucl_xxx_accession2taxid files

    This class is used to parse accession2taxid files.

    Args:
        acc_file (:obj:`str`): File to parse
        chunk (:obj:`int`): Chunk insert size. Default 500

    """

    def __init__(self, acc_file=None, chunk=500, fast=False, **kwargs):
        super().__init__(**kwargs)
        self.acc_file = acc_file
        self.chunk = chunk
        self.fast = fast

    def accession2taxid(self, acc2taxid=None, chunk=500):
        """Parses the accession2taxid files

        This method parses the accession2taxid file, build a dictionary,
            stores it in a list and yield for insertion in the database.

        ::

            {
                'accession': accession_id_from_file,
                'taxid': associated_taxonomic_id
            }


        Args:
            acc2taxid (:obj:`str`): Path to acc2taxid input file (gzipped)
            chunk (:obj:`int`): Chunk size of entries to gather before
                yielding. Default 500

        Yields:
            list: Chunk size of read entries

        """
        # Some accessions (e.g.: AAA22826) have a taxid = 0
        entries = []
        counter = 0
        taxids = {str(x['ncbi_taxid']): True for x in Taxa.select(
            Taxa.ncbi_taxid).dicts()}
        # Reach out of memory
        # accessions = {str(x['accession']): True for x in Accession.select(
        #     Accession.accession).dicts()}
        if not self.fast:
            accessions = {}
        if acc2taxid is None:
            acc2taxid = self.acc_file
        self.check_file(acc2taxid)
        if not chunk:
            chunk = self.chunk
        self.verbose("Parsing %s" % str(acc2taxid))
        with gzip.open(acc2taxid, 'rb') as f:
            f.readline()  # discard the header
            for line in f:
                line_list = line.decode().rstrip('\n').split('\t')
                # Check the taxid already exists and get its id
                if line_list[2] not in taxids:
                    continue
                # In case of an update or parsing an already inserted list of
                # accessions
                if not self.fast:
                    if line_list[0] in accessions:
                        continue
                    try:
                        acc_id = Accession.get(Accession.accession == line_list[0])
                    except Accession.DoesNotExist as err:
                        accessions[line_list[0]] = True
                    data_dict = {
                        'accession': line_list[0],
                        'taxid': line_list[2]
                    }
                    entries.append(data_dict)
                    counter += 1
                else:
                    data_dict = {
                        'accession': line_list[0],
                        'taxid': line_list[2]
                    }
                    entries.append(data_dict)
                    counter += 1
                if counter == chunk:
                    yield(entries)
                    entries = []
                    counter = 0
            if len(entries):
                yield(entries)

    def set_accession_file(self, acc_file):
        """Set the accession file to use

        Args:
            acc_file (:obj:`str`): File to be set

        Returns:
            True
        Raises:
            SystemExit: If `acc_file` is None or not a file (`check_file`)

        """
        if acc_file is None:
            fatal("Please provide an accession file to set")
        self.check_file(acc_file)
        self.acc_file = acc_file
        return True