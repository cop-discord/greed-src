import urllib.parse
from re import U

from .encryption.tiktok import *
from .exceptions import msToken, web_user_agent


class User:
    def __init__(self, api):
        self.api = api

        """
        Updating this later
        """
