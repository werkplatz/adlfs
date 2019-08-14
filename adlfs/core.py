# -*- coding: utf-8 -*-
from __future__ import print_function, division, absolute_import

import logging
import requests
from datetime import datetime


from azure.datalake.store import lib, AzureDLFileSystem
from fsspec import AbstractFileSystem
from fsspec.utils import infer_storage_options

logger = logging.getLogger(__name__)


class AzureDatalakeFileSystem(AzureDLFileSystem, AbstractFileSystem):
    
    
    """
    Access Azure Datalake Gen1 as if it were a file system.

    This exposes a filesystem-like API on top of Azure Datalake Storage

    Examples
    _________
    >>> adl = AzureDatalakeFileSystem(tenant_id="xxxx", client_id="xxxx", 
                                    client_secret="xxxx", store_name="storage_account"
                                    )
        adl.ls('')
        
        When used with Dask's read method, pass credentials as follows:
        
        dd.read_parquet("adl://folder/filename.xyz", storage_options={
            'tenant_id': TENANT_ID, 'client_id': CLIENT_ID, 
            'client_secret': CLIENT_SECRET, 'store_name': STORE_NAME,
        })

    Parameters
    __________P
    tenant_id:  string
        Azure tenant, also known as the subscription id
    client_id: string
        The username or serivceprincipal id
    client_secret: string
        The access key
    store_name: string (None)
        The name of the datalake account being accessed
    """

    def __init__(self, tenant_id, client_id, client_secret, store_name):
        AbstractFileSystem.__init__(self)
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.store_name = store_name
        self.do_connect()

    def do_connect(self):
        """Establish connection object."""
        token = lib.auth(tenant_id=self.tenant_id,
                        client_id=self.client_id,
                        client_secret=self.client_secret,
                        )
        AzureDLFileSystem.__init__(self, token=token,
                                   store_name=self.store_name)

    def _trim_filename(self, fn):
        """ Determine what kind of filestore this is and return the path """
        so = infer_storage_options(fn)
        fileparts = so['path']
        return fileparts

    def glob(self, path):
        """For a template path, return matching files"""
        adlpaths = self._trim_filename(path)
        filepaths = AzureDLFileSystem.glob(self, adlpaths)
        return filepaths

    def open(self, path, mode='rb'):
        adl_path = self._trim_filename(path)
        f = AzureDLFileSystem.open(self, adl_path, mode=mode)
        return f

    def ukey(self, path):
        adl_path = self._trim_filename(path)
        return tokenize(self.info(adl_path)['modificationTime'])

    def size(self, path):
        adl_path = self._trim_filename(path)
        return self.info(adl_path)['length']

    def __getstate__(self):
        dic = self.__dict__.copy()
        del dic['token']
        del dic['azure']
        logger.debug("Serialize with state: %s", dic)
        return dic

    def __setstate__(self, state):
        
        logger.debug("De-serialize with state: %s", state)
        self.__dict__.update(state)
        self.do_connect()
        

class AzureBlobFileSystem(AbstractFileSystem):
    
    """
    abfs[s]://<file_system>@<account_name>.dfs.core.windows.net/<path>/<file_name>

    file_system  = A container on the datalake
    account_name = The name of the storage account
    path         =  A forward slash representation of the directory structure
    file_name    = The name of an individual file in the directory
    """
    
    
    def __init__(self, tenant_id, client_id, client_secret, storage_account, token=None):

        super().__init__()
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.storage_account = storage_account
        self.token = token
        self.token_type = None
        self.connect()
        self.dns_suffix = '.dfs.core.windows.net'

    def connect(self):
        """ Fetch an OAUTh token using a ServicePrincipal """
        
        url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        header = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {"client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://storage.azure.com/.default",
                "grant_type": "client_credentials"}
        response = requests.post(url=url, headers=header, data=data).json()
        self.token_type=response['token_type']
        expires_in=response['expires_in']
        ext_expires_in=response['ext_expires_in']
        self.token=response['access_token']
        
    def _make_headers(self):
        headers = {'Content-Type': 'application/x-www-form-urlencoded',
                   'x-ms-version': '2019-02-02',
                   'Authorization': f'Bearer {self.token}'
                   }
        return headers
    
    def _make_base_url(self, filesystem):
        return f"https://{self.storage_account}{self.dns_suffix}/{filesystem}"
        
    def ls(self, filesystem: str, resource: str = 'filesystem', recursive: bool = False):
        """ These are the parameters to be passed via the API call """
        # We will start by creating the first of each of the verbs
        
        url = self._make_base_url(filesystem=filesystem)
        headers = self._make_headers()
        
        payload = {'resource': resource,
                   'recursive': recursive}
        
        response = requests.get(url=url, headers=headers, params=payload)
        print(url)
        print(response.url)
        print(response.json()) 

    def make_request(self, url, headers, payload):
        r = requests.get(url=url, headers=headers, params=payload)
        return r