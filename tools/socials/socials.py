import random
import string
from logging import getLogger
from typing import Any, List, Optional, Union

import aiohttp
import orjson
import requests
from bs4 import BeautifulSoup
from cashews import cache

from ._types import TikTokUser, UserResponse

log = getLogger(__name__)
cache.setup("mem://")
# session_id = "63574015048%3AOPozE3Jl6HncN5%3A25%3AAYcr7_FrHdIR3yZsZIX1BCrAhk259BFm8N5tXAgRpw"
# session_id = "here try this <@352190010998390796> 65582956535%3AhpRiz9027Dp4BM%3A26%3AAYe_JeEwMb74G_7CUOpRI2faeAYywhDMmYZpIyK3KA"
session_id = "65582956535:hpRiz9027Dp4BM:26:AYe_JeEwMb74G_7CUOpRI2faeAYywhDMmYZpIyK3KA"


def gen_token(size=10, symbols=False):
    """Gen CSRF or something else token"""
    chars = string.ascii_letters + string.digits
    if symbols:
        chars += string.punctuation
    return "".join(random.choice(chars) for _ in range(size))


async def get_instagram_user(username: str) -> Optional[UserResponse]:
    csrf_token = gen_token()
    headers = {
        "sec-ch-ua-model": '"Nexus 5"',
        "sec-ch-ua-platform-version": '"6.0"',
        "sec-gpc": "1",
        "x-asbd-id": "129477",
        "x-csrftoken": csrf_token,
        "x-ig-app-id": "1217981644879628",
        "x-ig-www-claim": "hmac.AR2zzNBrpIQLgsg0anZmqob1QVOF2mi4xu9a8jZlMs6W6zAp",
        "x-requested-with": "XMLHttpRequest",
    }
    cookies = {
        "mid": "ZU6WxQALAAHJAd-CBWpdYdspSZMR",
        "datr": "xJZOZeFz-LCwjpznqK-zVtG8",
        "ds_user_id": "63019138462",
        "ig_did": "6398A16E-2B52-4D7A-971C-CD3B19ABC563",
        "ps_n": "0",
        "ps_l": "0",
        "ig_did": "0C826C21-17C3-444A-ABB7-EBABD37214D7",
        "shbid": '"1389\\05463019138462\\0541739052557:01f72cc7666412cb25c056db7dbc28a4a0a2c3a389ee525d47dc1fe2173b66e9972a82b1"',
        "shbts": '"1707516557\\05463019138462\\0541739052557:01f786801a344976db73dbb23e7276adc063189c3327e7cbff3f360e88268c86b13215fa"',
        "sessionid": session_id,
        "dpr": "2",
        "rur": '"EAG\\05463019138462\\0541739054606:01f73d1e38c984458222a7b8afa73fe2810b5c85a953b46b412f57842e17bb0fc36d5eaf"',
    }
    async with aiohttp.ClientSession() as session:
        async with session.request(
            "GET",
            f"https://www.instagram.com/api/v1/users/web_profile_info/",
            params={"username": username},
            proxy=None,  # random.choice(proxies),
            headers=headers,
            max_redirects=30,
            cookies=cookies,
        ) as response:
            data = await response.json()
    return UserResponse(**data)


async def get_tiktok_user(username: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"https://tiktok.com/embed/@{username}",
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            },
        ) as f:
            if f.status == 404:
                return None
            html = await f.text()
    soup = BeautifulSoup(html, "html.parser")
    data = orjson.loads(
        str(
            soup.find(
                "script",
                attrs={"id": "__FRONTITY_CONNECT_STATE__", "type": "application/json"},
            ).contents[0]
        )
    )
    user = data["source"]["data"][f"/embed/@{username}"]["userInfo"]
    followers = user["followerCount"]
    following = user["followingCount"]
    likes = user["heartCount"]
    display = user["nickname"]
    bio = user["signature"]
    # soup=BeautifulSoup(html,"html.parser")
    # priv_data=soup.find('p',attrs={'class':'tiktok-1c74ckh-PTitle emuynwa1'})
    avatar = user["avatarThumbUrl"]
    profile_url = f"https://tiktok.com/@{username}"
    private = user["privateAccount"]
    verified = user["verified"]
    data = {
        "username": username,
        "display": display,
        "followers": followers,
        "following": following,
        "likes": likes,
        "verified": verified,
        "private": private,
        "bio": bio,
        "url": profile_url,
        "avatar": avatar,
    }
    return TikTokUser(**data)
