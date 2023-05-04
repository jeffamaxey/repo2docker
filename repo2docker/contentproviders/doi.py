import os
import json
import shutil
import logging

from os import makedirs
from os import path
from requests import Session, HTTPError

from zipfile import ZipFile, is_zipfile

from .base import ContentProvider
from ..utils import copytree, deep_get
from ..utils import normalize_doi, is_doi
from .. import __version__


class DoiProvider(ContentProvider):
    """Provide contents of a repository identified by a DOI and some helper functions."""

    def __init__(self):
        super().__init__()
        self.session = Session()
        self.session.headers.update({"user-agent": f"repo2docker {__version__}"})

    def _request(self, url, **kwargs):
        return self.session.get(url, **kwargs)

    urlopen = _request

    def _urlopen(self, req, headers=None):
        """A urlopen() helper"""
        # someone passed a string, not a request
        if not isinstance(req, request.Request):
            req = request.Request(req)

        req.add_header("User-Agent", f"repo2docker {__version__}")
        if headers is not None:
            for key, value in headers.items():
                req.add_header(key, value)

        return request.urlopen(req)

    def doi2url(self, doi):
        if not is_doi(doi):
            # Just return what is actulally just a URL
            return doi
        doi = normalize_doi(doi)

        try:
            resp = self._request(f"https://doi.org/{doi}")
            resp.raise_for_status()
        except HTTPError:
            return doi
        return resp.url

    def fetch_file(self, file_ref, host, output_dir, unzip=False):
        # the assumption is that `unzip=True` means that this is the only
        # file related to a record
        file_url = deep_get(file_ref, host["download"])
        fname = deep_get(file_ref, host["filename"])
        logging.debug(f"Downloading file {file_url} as {fname}\n")

        yield f"Requesting {file_url}\n"
        resp = self._request(file_url, stream=True)
        resp.raise_for_status()

        if path.dirname(fname):
            sub_dir = path.join(output_dir, path.dirname(fname))
            if not path.exists(sub_dir):
                yield f"Creating {sub_dir}\n"
                makedirs(sub_dir, exist_ok=True)

        dst_fname = path.join(output_dir, fname)
        with open(dst_fname, "wb") as dst:
            yield f"Fetching {fname}\n"
            for chunk in resp.iter_content(chunk_size=None):
                dst.write(chunk)

        if unzip and is_zipfile(dst_fname):
            yield f"Extracting {fname}\n"
            zfile = ZipFile(dst_fname)
            zfile.extractall(path=output_dir)
            zfile.close()

            # delete downloaded file ...
            os.remove(dst_fname)
            # ... and any directories we might have created,
            # in which case sub_dir will be defined
            if path.dirname(fname):
                shutil.rmtree(sub_dir)

            new_subdirs = os.listdir(output_dir)
            # if there is only one new subdirectory move its contents
            # to the top level directory
            if len(new_subdirs) == 1:
                d = new_subdirs[0]
                copytree(path.join(output_dir, d), output_dir)
                shutil.rmtree(path.join(output_dir, d))

            yield f"Fetched files: {os.listdir(output_dir)}\n"
