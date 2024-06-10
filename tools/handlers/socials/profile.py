from typing import Optional

from pydantic import BaseModel


class ServerProfile(BaseModel):
    """
    Model for discord server profiles
    """

    banner: Optional[str]
    bio: Optional[str]
