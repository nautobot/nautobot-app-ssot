import re

def get_id_from_url(url: str):
    """Get Cradlepoint object ID from url string."""
    url = re.sub(r"\?.*", "", url)
    id_str = url.rstrip("/").split("/")[-1]
    try:
        return int(id_str)
    except ValueError:
        return None