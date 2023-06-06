"""ACI Utilities."""
import logging
import re
import yaml

logger = logging.getLogger("rq.worker")


def pod_from_dn(dn):
    """Match an ACI pod_id in the Distiguished Name (DN)."""
    pattern = r"/pod-(?P<pod>\d+)"
    return (re.search(pattern, dn)).group("pod")


def node_from_dn(dn):
    """Match an ACI node_id in the Distiguished Name (DN)."""
    pattern = r"/node-(?P<node>\d+)"
    return (re.search(pattern, dn)).group("node")


def interface_from_dn(dn):
    """Match an ACI port in the Distiguished Name (DN)."""
    pattern = r"phys-.(?P<int>.*)."
    return (re.search(pattern, dn)).group("int")


def fex_id_from_dn(dn):
    """Match an ACI fex_id from port in the Distiguished Name (DN)."""
    pattern = r"phys-.eth(?P<fex>\d*)/.+"
    return (re.search(pattern, dn)).group("fex")


def tenant_from_dn(dn):
    """Match an ACI tenant in the Distiguished Name (DN)."""
    pattern = "tn-(.+?)\/"  # noqa: W605  # pylint: disable=anomalous-backslash-in-string
    return re.search(pattern, dn).group().replace("tn-", "", 1).rstrip("/")


def ap_from_dn(dn):
    """Match an ACI Application Profile in the Distinguished Name (DN)."""
    pattern = "ap-[A-Za-z0-9\-]+"  # noqa: W605 # pylint: disable=anomalous-backslash-in-string
    return re.search(pattern, dn).group().replace("ap-", "", 1).rstrip("/")


def load_yamlfile(filename):
    """Load a YAML file to a Dict."""
    with open(filename, "r", encoding="utf-8") as fn:
        yaml_file = yaml.safe_load(fn)
    return yaml_file
